-- migrations/005_pai_gow.sql
-- Pai Gow Poker (house-banked) — schema additions.
--
-- Owner: halynk21
--
-- This migration is ADDITIVE ONLY. Zero ALTER on existing tables. PG owns its
-- full container schema (mirrors poker_tournaments / poker_seats / poker_hands
-- from 002_poker.sql). The only existing table referenced is `users` (FK only,
-- chip_balance read/write happens via app code, not in this migration).
--
-- Idempotent: uses CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
-- Tests use Base.metadata.create_all (in-memory SQLite) — this file is only
-- exercised by the CI Postgres job.
--
-- See specs/pai-gow.md §8 (data model), §9 (state machine), §11 (Fortune pool).


-- ─── Pai Gow Tables ──────────────────────────────────────────────────────────
-- One row per PG table. Long-lived; many rounds played per table over time.

CREATE TABLE IF NOT EXISTS pai_gow_tables (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                     TEXT NOT NULL,
  min_bet_cents            INTEGER NOT NULL DEFAULT 500
                              CHECK (min_bet_cents > 0),
  max_bet_cents            INTEGER NOT NULL DEFAULT 50000
                              CHECK (max_bet_cents >= min_bet_cents),
  min_fortune_bet_cents    INTEGER NOT NULL DEFAULT 100
                              CHECK (min_fortune_bet_cents >= 0),
  max_fortune_bet_cents    INTEGER NOT NULL DEFAULT 10000
                              CHECK (max_fortune_bet_cents >= min_fortune_bet_cents),
  max_seats                INTEGER NOT NULL DEFAULT 3
                              CHECK (max_seats BETWEEN 1 AND 3),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── Pai Gow Seats ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pai_gow_seats (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id                 UUID NOT NULL REFERENCES pai_gow_tables(id) ON DELETE CASCADE,
  user_id                  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  seat_number              INTEGER NOT NULL CHECK (seat_number BETWEEN 1 AND 3),
  joined_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (table_id, seat_number),
  UNIQUE (table_id, user_id)
);


-- ─── Pai Gow Rounds ──────────────────────────────────────────────────────────
-- One row per round of play. Multiple rounds per table over time.
-- playing_started_at is the AUTHORITATIVE timeout reference (spec §9.4).
-- UNIQUE(table_id, round_number) is what makes the round-creation race fix B
-- in spec §9.2 deterministic — second simultaneous first-deal gets IntegrityError
-- on this constraint and retries.

CREATE TABLE IF NOT EXISTS pai_gow_rounds (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id                 UUID NOT NULL REFERENCES pai_gow_tables(id) ON DELETE CASCADE,
  round_number             INTEGER NOT NULL,
  dealer_dealt_cards       JSONB NOT NULL DEFAULT '[]'::jsonb,
  dealer_front             JSONB,
  dealer_back              JSONB,
  deck_state               JSONB NOT NULL DEFAULT '[]'::jsonb,
  status                   TEXT NOT NULL DEFAULT 'betting'
                              CHECK (status IN ('betting','playing','dealer_turn','finished')),
  playing_started_at       TIMESTAMPTZ,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at              TIMESTAMPTZ,
  UNIQUE (table_id, round_number)
);


-- ─── Pai Gow Player Hands ────────────────────────────────────────────────────
-- One row per (round, user). Stores dealt 7 cards + chosen 2/5 split + compare
-- results + payouts. created_at is for audit/replay only — NOT a timeout source
-- (round-level playing_started_at is authoritative, spec §9.4).

CREATE TABLE IF NOT EXISTS pai_gow_player_hands (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  round_id                 UUID NOT NULL REFERENCES pai_gow_rounds(id) ON DELETE CASCADE,
  user_id                  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dealt_cards              JSONB NOT NULL,
  front_cards              JSONB,
  back_cards               JSONB,
  bet_cents                INTEGER NOT NULL CHECK (bet_cents > 0),
  fortune_bet_cents        INTEGER NOT NULL DEFAULT 0
                              CHECK (fortune_bet_cents >= 0),
  front_compare            TEXT
                              CHECK (front_compare IS NULL OR front_compare IN ('player','banker','copy')),
  back_compare             TEXT
                              CHECK (back_compare IS NULL OR back_compare IN ('player','banker','copy')),
  hand_result              TEXT
                              CHECK (hand_result IS NULL OR hand_result IN ('win','push','lose')),
  ante_payout_cents        INTEGER,
  fortune_payout_cents     INTEGER,
  action_status            TEXT NOT NULL DEFAULT 'dealt'
                              CHECK (action_status IN ('dealt','set','auto_set','resolved')),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at              TIMESTAMPTZ,
  UNIQUE (round_id, user_id)
);


-- ─── Pai Gow Player Actions (replay audit trail) ─────────────────────────────
-- One row per set/auto_set event. Drives the hand-replay UI and the streak
-- update (was_optimal field). Note action_type does NOT include 'forfeit' —
-- forfeit is v2 (spec §15).

CREATE TABLE IF NOT EXISTS pai_gow_player_actions (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hand_id                  UUID NOT NULL REFERENCES pai_gow_player_hands(id) ON DELETE CASCADE,
  user_id                  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  action_type              TEXT NOT NULL
                              CHECK (action_type IN ('set','auto_set')),
  player_front             JSONB,
  player_back              JSONB,
  optimal_front            JSONB NOT NULL,
  optimal_back             JSONB NOT NULL,
  was_optimal              BOOLEAN NOT NULL,
  chipy_explanation        TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── Pai Gow Strategy Streaks ────────────────────────────────────────────────
-- Per-user PG-specific streak. Separate from users.current_streak / best_streak
-- which stay blackjack-owned (round-4 decision; spec §15 documents the
-- known inconsistency, v2 may unify under generic strategy_streak(game_type)).

CREATE TABLE IF NOT EXISTS pai_gow_strategy_streaks (
  user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  current_streak           INTEGER NOT NULL DEFAULT 0,
  longest_streak           INTEGER NOT NULL DEFAULT 0,
  total_optimal            INTEGER NOT NULL DEFAULT 0,
  total_played             INTEGER NOT NULL DEFAULT 0,
  last_played_at           TIMESTAMPTZ
);


-- ─── Fortune Pool (singleton row) ────────────────────────────────────────────
-- Sentinel UUID '00000000-0000-0000-0000-000000000001' identifies the singleton.
-- All concurrent updates serialize on this row via SELECT … FOR UPDATE in §11.4.
-- amount_cents is BIGINT because the pool can grow large (millions of cents).
-- CHECK enforces the seed_cents floor (pool can never go below seed).

CREATE TABLE IF NOT EXISTS fortune_pool (
  id                       UUID PRIMARY KEY,
  amount_cents             BIGINT NOT NULL DEFAULT 100000,
  seed_cents               BIGINT NOT NULL DEFAULT 100000,
  last_updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (amount_cents >= seed_cents)
);

-- Seed the singleton row. Idempotent via ON CONFLICT.
INSERT INTO fortune_pool (id, amount_cents, seed_cents, last_updated_at)
VALUES ('00000000-0000-0000-0000-000000000001', 100000, 100000, NOW())
ON CONFLICT (id) DO NOTHING;


-- ─── Fortune Pool Events (audit ledger) ──────────────────────────────────────
-- One row per contribute / payout / seed event. The demo reads from here to
-- show the math. Concurrency tests verify ledger-based invariants (spec §11.6).

CREATE TABLE IF NOT EXISTS fortune_pool_events (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hand_id                  UUID REFERENCES pai_gow_player_hands(id) ON DELETE SET NULL,
  event_type               TEXT NOT NULL
                              CHECK (event_type IN ('seed','contribute','fixed_payout','grand_payout','major_payout')),
  contribution_cents       BIGINT NOT NULL DEFAULT 0,
  payout_cents             BIGINT NOT NULL DEFAULT 0,
  post_balance_cents       BIGINT NOT NULL,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed event for the initial pool. Idempotent: only insert if no seed event exists.
INSERT INTO fortune_pool_events (event_type, contribution_cents, payout_cents, post_balance_cents)
SELECT 'seed', 100000, 0, 100000
WHERE NOT EXISTS (SELECT 1 FROM fortune_pool_events WHERE event_type = 'seed');


-- ─── Indexes ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pai_gow_seats_table              ON pai_gow_seats(table_id);
CREATE INDEX IF NOT EXISTS idx_pai_gow_seats_user               ON pai_gow_seats(user_id);
CREATE INDEX IF NOT EXISTS idx_pai_gow_rounds_table_status      ON pai_gow_rounds(table_id, status);
CREATE INDEX IF NOT EXISTS idx_pai_gow_player_hands_round_status ON pai_gow_player_hands(round_id, action_status);
CREATE INDEX IF NOT EXISTS idx_pai_gow_player_hands_user        ON pai_gow_player_hands(user_id);
CREATE INDEX IF NOT EXISTS idx_pai_gow_player_actions_hand      ON pai_gow_player_actions(hand_id);
CREATE INDEX IF NOT EXISTS idx_fortune_pool_events_hand         ON fortune_pool_events(hand_id);
CREATE INDEX IF NOT EXISTS idx_fortune_pool_events_created      ON fortune_pool_events(created_at DESC);
