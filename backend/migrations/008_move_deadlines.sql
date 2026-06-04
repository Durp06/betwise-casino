-- 008_move_deadlines.sql
-- Per-player move timer (specs/move-timer-and-time-cards.md, PR1).
--
-- Adds the server-authoritative absolute move deadline to the row that holds
-- each game's turn pointer:
--   * holdem_hands.move_deadline_at  — alongside current_to_act_seat
--   * hands.move_deadline_at         — the blackjack current-actor hand
--
-- The instant is non-null only while a human is on the clock; enforcement is
-- lazy (resolved on the next /state poll or /act). See routers/holdem.py
-- ::_enforce_move_timeout and routers/game.py / game/blackjack/state.py.
--
-- DEPLOY: applied automatically at container startup by backend/migrate.py and
-- recorded in the schema_migrations ledger. Additive + idempotent
-- (ADD COLUMN IF NOT EXISTS) — safe to run multiple times. Tests build the
-- schema from Base.metadata.create_all, not this file, so the ORM column in
-- models.py is the source of truth for the test suite; keep the two in sync.

ALTER TABLE holdem_hands ADD COLUMN IF NOT EXISTS move_deadline_at TIMESTAMPTZ;
ALTER TABLE hands ADD COLUMN IF NOT EXISTS move_deadline_at TIMESTAMPTZ;
