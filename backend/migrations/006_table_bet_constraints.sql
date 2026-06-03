-- 006_table_bet_constraints.sql
-- Add CHECK constraints to casino_tables for min_bet and max_bet validation.
-- Idempotent: safe to run multiple times.

-- Add min_bet > 0 constraint if it doesn't already exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'min_bet_positive'
          AND conrelid = 'casino_tables'::regclass
    ) THEN
        ALTER TABLE casino_tables
            ADD CONSTRAINT min_bet_positive
            CHECK (min_bet > 0);
    END IF;
END
$$;

-- Add max_bet >= min_bet constraint if it doesn't already exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'max_bet_ge_min_bet'
          AND conrelid = 'casino_tables'::regclass
    ) THEN
        ALTER TABLE casino_tables
            ADD CONSTRAINT max_bet_ge_min_bet
            CHECK (max_bet >= min_bet);
    END IF;
END
$$;
