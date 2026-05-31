-- migrations/003_holdem.sql
-- Multiplayer Texas Hold'em (cash ring game) tables.
-- Idempotent: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
-- Tests use Base.metadata.create_all (in-memory SQLite) — this file is only
-- exercised by the CI/Railway Postgres deploy. Seat numbers are 0-based to
-- match the betting engine. Chips are integer fake-cents (same unit as
-- users.chip_balance): a buy-in deducts the bankroll, a cash-out credits it.

CREATE TABLE IF NOT EXISTS holdem_tables (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    small_blind   INTEGER NOT NULL DEFAULT 50  CHECK (small_blind > 0),
    big_blind     INTEGER NOT NULL DEFAULT 100 CHECK (big_blind >= small_blind),
    min_buy_in    INTEGER NOT NULL DEFAULT 2000  CHECK (min_buy_in > 0),
    max_buy_in    INTEGER NOT NULL DEFAULT 20000 CHECK (max_buy_in >= min_buy_in),
    max_seats     INTEGER NOT NULL DEFAULT 6 CHECK (max_seats BETWEEN 2 AND 9),
    button_pos    INTEGER,
    status        VARCHAR(20) NOT NULL DEFAULT 'waiting'
                     CHECK (status IN ('waiting','playing')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS holdem_seats (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id      UUID NOT NULL REFERENCES holdem_tables(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seat_number   INTEGER NOT NULL CHECK (seat_number >= 0),
    stack         INTEGER NOT NULL CHECK (stack >= 0),
    status        VARCHAR(20) NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','sitting_out')),
    joined_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (table_id, seat_number),
    UNIQUE (table_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_holdem_seats_table ON holdem_seats(table_id);
CREATE INDEX IF NOT EXISTS idx_holdem_seats_user ON holdem_seats(user_id);

CREATE TABLE IF NOT EXISTS holdem_hands (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id               UUID NOT NULL REFERENCES holdem_tables(id) ON DELETE CASCADE,
    hand_number            INTEGER NOT NULL,
    button_seat            INTEGER NOT NULL,
    deck                   JSONB NOT NULL DEFAULT '[]'::jsonb,
    small_blind            INTEGER NOT NULL,
    big_blind              INTEGER NOT NULL,
    board                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    pot_total              INTEGER NOT NULL DEFAULT 0,
    side_pots              JSONB NOT NULL DEFAULT '[]'::jsonb,
    street                 VARCHAR(20) NOT NULL DEFAULT 'preflop'
                              CHECK (street IN ('preflop','flop','turn','river','complete')),
    current_bet_to_match   INTEGER NOT NULL DEFAULT 0,
    current_to_act_seat    INTEGER,
    last_aggressor_seat    INTEGER,
    min_raise_increment    INTEGER NOT NULL DEFAULT 0,
    status                 VARCHAR(20) NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active','complete')),
    result                 JSONB,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (table_id, hand_number)
);

CREATE INDEX IF NOT EXISTS idx_holdem_hands_table ON holdem_hands(table_id);

CREATE TABLE IF NOT EXISTS holdem_hand_seats (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hand_id                UUID NOT NULL REFERENCES holdem_hands(id) ON DELETE CASCADE,
    seat_number            INTEGER NOT NULL,
    user_id                UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    table_seat_number      INTEGER NOT NULL,
    hole_cards             JSONB NOT NULL DEFAULT '[]'::jsonb,
    starting_stack         INTEGER NOT NULL,
    final_stack            INTEGER NOT NULL,
    contributed            INTEGER NOT NULL DEFAULT 0,
    current_bet            INTEGER NOT NULL DEFAULT 0,
    is_folded              BOOLEAN NOT NULL DEFAULT FALSE,
    is_all_in              BOOLEAN NOT NULL DEFAULT FALSE,
    has_acted_this_street  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (hand_id, seat_number)
);

CREATE INDEX IF NOT EXISTS idx_holdem_hand_seats_hand ON holdem_hand_seats(hand_id);

CREATE TABLE IF NOT EXISTS holdem_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hand_id         UUID NOT NULL REFERENCES holdem_hands(id) ON DELETE CASCADE,
    seat_number     INTEGER NOT NULL,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    action_index    INTEGER NOT NULL,
    street          VARCHAR(20) NOT NULL,
    action          VARCHAR(20) NOT NULL
                       CHECK (action IN ('fold','check','call','raise',
                                         'all_in','post_blind','post_ante')),
    amount          INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (hand_id, action_index)
);

CREATE INDEX IF NOT EXISTS idx_holdem_actions_hand ON holdem_actions(hand_id);
CREATE INDEX IF NOT EXISTS idx_holdem_actions_user ON holdem_actions(user_id);
