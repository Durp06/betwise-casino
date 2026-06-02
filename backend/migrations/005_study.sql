-- BetWise Casino — Study Migration
-- Version: 003
-- Author: BetWise Casino team
--
-- How to run:
--   Option A (Supabase): Paste into the Supabase SQL editor and execute.
--   Option B (psql):     psql $DATABASE_URL -f 003_study.sql
--
-- This migration is IDEMPOTENT — safe to run multiple times.
-- All ALTER TABLE statements use ADD COLUMN IF NOT EXISTS guards.
-- Indexes use CREATE INDEX IF NOT EXISTS.
-- Constraints use a DO block with IF NOT EXISTS logic.
--
-- Changes:
--   - hands.created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
--   - idx_hands_user_created index on hands(user_id, created_at DESC)
--   - users.total_decisions INTEGER NOT NULL DEFAULT 0 CHECK (>= 0)

-- ─── hands.created_at ─────────────────────────────────────────────────────────

ALTER TABLE hands
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_hands_user_created
    ON hands (user_id, created_at DESC);

-- ─── users.total_decisions ────────────────────────────────────────────────────

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS total_decisions INTEGER NOT NULL DEFAULT 0;

-- Add CHECK constraint if it doesn't already exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'total_decisions_non_negative'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT total_decisions_non_negative
            CHECK (total_decisions >= 0);
    END IF;
END
$$;
