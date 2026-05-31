-- migrations/002_poker.sql
-- Texas Hold'em tournament tables.
-- Idempotent: uses CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
-- Tests use Base.metadata.create_all (in-memory SQLite) — this file is
-- only exercised by the CI Postgres job.

CREATE TABLE IF NOT EXISTS poker_tournaments (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_count              INTEGER NOT NULL CHECK (bot_count BETWEEN 2 AND 7),
    advice_mode            VARCHAR(10) NOT NULL DEFAULT 'odds'
                              CHECK (advice_mode IN ('reads','odds')),
    buy_in_cents           INTEGER NOT NULL CHECK (buy_in_cents > 0),
    starting_stack_chips   INTEGER NOT NULL DEFAULT 1500
                              CHECK (starting_stack_chips > 0),
    hands_per_level        INTEGER NOT NULL DEFAULT 10,
    seed                   INTEGER NOT NULL,
    status                 VARCHAR(20) NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active','complete','aborted')),
    button_seat            INTEGER NOT NULL DEFAULT 0,
    current_hand_number    INTEGER NOT NULL DEFAULT 0,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS poker_seats (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id       UUID NOT NULL REFERENCES poker_tournaments(id) ON DELETE CASCADE,
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,  -- NULL = bot
    seat_number         INTEGER NOT NULL,
    archetype_name      VARCHAR(40),
    starting_stack      INTEGER NOT NULL CHECK (starting_stack >= 0),
    current_stack       INTEGER NOT NULL CHECK (current_stack >= 0),
    is_bust             BOOLEAN NOT NULL DEFAULT FALSE,
    bust_position       INTEGER,
    is_bot              BOOLEAN NOT NULL DEFAULT FALSE,
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tournament_id, seat_number)
);

CREATE INDEX IF NOT EXISTS idx_poker_seats_tournament ON poker_seats(tournament_id);
CREATE INDEX IF NOT EXISTS idx_poker_seats_user ON poker_seats(user_id);

CREATE TABLE IF NOT EXISTS poker_hands (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id            UUID NOT NULL REFERENCES poker_tournaments(id) ON DELETE CASCADE,
    hand_number              INTEGER NOT NULL,
    button_seat              INTEGER NOT NULL,
    seed                     INTEGER NOT NULL,
    small_blind              INTEGER NOT NULL,
    big_blind                INTEGER NOT NULL,
    ante                     INTEGER NOT NULL DEFAULT 0,
    board                    JSONB NOT NULL DEFAULT '[]'::jsonb,
    pot_total                INTEGER NOT NULL DEFAULT 0,
    side_pots                JSONB NOT NULL DEFAULT '[]'::jsonb,
    street                   VARCHAR(20) NOT NULL DEFAULT 'preflop'
                                CHECK (street IN ('preflop','flop','turn','river','complete')),
    current_bet_to_match     INTEGER NOT NULL DEFAULT 0,
    current_to_act_seat      INTEGER,
    last_aggressor_seat      INTEGER,
    min_raise_increment      INTEGER NOT NULL DEFAULT 0,
    status                   VARCHAR(20) NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active','complete','aborted')),
    result                   JSONB,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tournament_id, hand_number)
);

CREATE INDEX IF NOT EXISTS idx_poker_hands_tournament ON poker_hands(tournament_id);

CREATE TABLE IF NOT EXISTS poker_hand_seats (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hand_id                  UUID NOT NULL REFERENCES poker_hands(id) ON DELETE CASCADE,
    seat_number              INTEGER NOT NULL,
    hole_cards               JSONB NOT NULL DEFAULT '[]'::jsonb,
    starting_stack           INTEGER NOT NULL,
    final_stack              INTEGER NOT NULL,
    contributed              INTEGER NOT NULL DEFAULT 0,
    current_bet              INTEGER NOT NULL DEFAULT 0,
    is_folded                BOOLEAN NOT NULL DEFAULT FALSE,
    is_all_in                BOOLEAN NOT NULL DEFAULT FALSE,
    has_acted_this_street    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (hand_id, seat_number)
);

CREATE INDEX IF NOT EXISTS idx_poker_hand_seats_hand ON poker_hand_seats(hand_id);

CREATE TABLE IF NOT EXISTS poker_actions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hand_id                  UUID NOT NULL REFERENCES poker_hands(id) ON DELETE CASCADE,
    seat_number              INTEGER NOT NULL,
    user_id                  UUID REFERENCES users(id) ON DELETE CASCADE,
    action_index             INTEGER NOT NULL,
    street                   VARCHAR(20) NOT NULL,
    action                   VARCHAR(20) NOT NULL
                                CHECK (action IN ('fold','check','call','raise',
                                                  'all_in','post_blind','post_ante')),
    amount                   INTEGER NOT NULL DEFAULT 0,
    recommended_action       VARCHAR(20),
    confidence_tier          VARCHAR(20)
                                CHECK (confidence_tier IS NULL
                                       OR confidence_tier IN ('DETERMINISTIC','HEURISTIC')),
    verdict                  VARCHAR(20),
    ev_loss_chips            INTEGER,
    live_equity              DOUBLE PRECISION,
    chipy_explanation        TEXT,
    is_human                 BOOLEAN NOT NULL DEFAULT FALSE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (hand_id, action_index)
);

CREATE INDEX IF NOT EXISTS idx_poker_actions_hand ON poker_actions(hand_id);
CREATE INDEX IF NOT EXISTS idx_poker_actions_user ON poker_actions(user_id);
