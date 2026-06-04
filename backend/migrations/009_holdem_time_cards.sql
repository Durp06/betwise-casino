-- 009_holdem_time_cards.sql
-- Hold'em time cards (specs/move-timer-and-time-cards.md, PR2).
--
-- Each player is granted 5 time cards when they take a seat; using one extends
-- the current move clock by +15s and decrements the count (no regen during
-- play). The count lives on the seat row, so a leave/rejoin grants a fresh 5.
-- See routers/holdem.py::_use_time_card and _join_seat.
--
-- DEPLOY: applied automatically at container startup by backend/migrate.py.
-- Additive + idempotent (ADD COLUMN IF NOT EXISTS; the CHECK is added inside a
-- DO block that swallows duplicate_object, since Postgres has no
-- ADD CONSTRAINT IF NOT EXISTS). Safe to run multiple times. Tests build the
-- schema from Base.metadata.create_all, so the ORM column/constraint in
-- models.py is the source of truth for the suite; keep the two in sync.

ALTER TABLE holdem_seats
  ADD COLUMN IF NOT EXISTS time_cards_remaining INTEGER NOT NULL DEFAULT 5;

DO $$ BEGIN
  ALTER TABLE holdem_seats
    ADD CONSTRAINT holdem_seat_time_cards_nonneg CHECK (time_cards_remaining >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
