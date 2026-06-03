-- 007_hand_advice_graded.sql
-- Add idempotency column to hands table for streak-replay protection.
-- The column records len(hand.cards) at the time the streak was last graded,
-- so advice.py can skip the streak mutation on a replay of the same decision.
-- Idempotent: safe to run multiple times.

ALTER TABLE hands ADD COLUMN IF NOT EXISTS advice_graded_card_count INTEGER;
