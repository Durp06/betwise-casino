-- BetWise Casino — Initial Database Migration
-- Version: 001
-- Author: BetWise Casino team
--
-- How to run:
--   Option A (Supabase): Paste into the Supabase SQL editor and execute.
--   Option B (psql):     psql $DATABASE_URL -f 001_initial.sql
--
-- This migration is IDEMPOTENT — safe to run multiple times.
-- All CREATE statements use IF NOT EXISTS guards.
-- Indexes use CREATE INDEX IF NOT EXISTS.
--
-- Schema additions vs. source spec:
--   - users.current_streak, users.best_streak (gold: streak system)
--   - game_sessions.game_type (extensibility for future games)


-- ─── Users ────────────────────────────────────────────────────────────────────
-- One row per Supabase Auth user. ID matches auth.users.id.

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username TEXT UNIQUE NOT NULL CHECK (char_length(username) BETWEEN 3 AND 20),
  chip_balance INTEGER NOT NULL DEFAULT 100000 CHECK (chip_balance >= 0),
  total_hands INTEGER NOT NULL DEFAULT 0,
  correct_decisions INTEGER NOT NULL DEFAULT 0,
  current_streak INTEGER NOT NULL DEFAULT 0,
  best_streak INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── Casino Tables ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS casino_tables (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  min_bet INTEGER NOT NULL DEFAULT 500,
  max_bet INTEGER NOT NULL DEFAULT 50000,
  max_seats INTEGER NOT NULL DEFAULT 3,
  status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','playing','finished')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── Table Seats ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS table_seats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id UUID NOT NULL REFERENCES casino_tables(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  seat_number INTEGER NOT NULL CHECK (seat_number BETWEEN 1 AND 3),
  joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(table_id, seat_number),
  UNIQUE(table_id, user_id)
);


-- ─── Game Sessions ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS game_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id UUID NOT NULL REFERENCES casino_tables(id) ON DELETE CASCADE,
  game_type TEXT NOT NULL DEFAULT 'blackjack',
  dealer_cards JSONB NOT NULL DEFAULT '[]',
  deck_state JSONB NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'betting' CHECK (status IN ('betting','playing','dealer_turn','finished')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── Hands ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS hands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  cards JSONB NOT NULL DEFAULT '[]',
  bet INTEGER NOT NULL CHECK (bet >= 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','standing','bust','blackjack','finished')),
  outcome TEXT CHECK (outcome IN ('win','loss','push','blackjack','bust')),
  payout INTEGER,
  UNIQUE(session_id, user_id)
);


-- ─── Player Actions ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS player_actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hand_id UUID NOT NULL REFERENCES hands(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  action TEXT NOT NULL CHECK (action IN ('hit','stand','double','split')),
  player_guess TEXT NOT NULL CHECK (player_guess IN ('hit','stand','double','split')),
  optimal_action TEXT NOT NULL CHECK (optimal_action IN ('hit','stand','double','split')),
  was_correct BOOLEAN NOT NULL,
  hand_snapshot JSONB NOT NULL,
  dealer_upcard JSONB NOT NULL,
  chipy_explanation TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─── Indexes ──────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_player_actions_user_id ON player_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_player_actions_hand_id ON player_actions(hand_id);
CREATE INDEX IF NOT EXISTS idx_hands_session_id ON hands(session_id);
CREATE INDEX IF NOT EXISTS idx_table_seats_table_id ON table_seats(table_id);
CREATE INDEX IF NOT EXISTS idx_game_sessions_table_id ON game_sessions(table_id);
