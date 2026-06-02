-- migrations/004_chat.sql
-- In-game player chat, polymorphic across both multiplayer games (blackjack +
-- multiplayer Hold'em).
-- Idempotent: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.
-- Tests use Base.metadata.create_all (in-memory SQLite) — this file is only
-- exercised by the CI/Railway Postgres deploy.
--
-- `table_id` is NOT a foreign key: it polymorphically references either
-- casino_tables(id) or holdem_tables(id), discriminated by `table_kind`. The
-- router enforces that the poster is seated at that table before inserting.
-- `body` is stored VERBATIM (server validates + strips control chars but never
-- HTML-escapes); the React client renders it as an inert text node, so pasted
-- markup like <script> cannot execute (stored-XSS defense).

CREATE TABLE IF NOT EXISTS chat_messages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_kind    VARCHAR(20) NOT NULL
                     CHECK (table_kind IN ('blackjack','holdem')),
    table_id      UUID NOT NULL,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username      VARCHAR(20) NOT NULL,
    body          TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_table
    ON chat_messages(table_kind, table_id, created_at);
