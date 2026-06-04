-- 008_centralize_starting_balance.sql
-- Centralize the starting bankroll at 5,000,000 cents ($50,000.00).
-- 5000000 MUST match backend/models.py::STARTING_BALANCE_CENTS.
-- Idempotent: re-running sets the same DEFAULT and the same balance.

ALTER TABLE users ALTER COLUMN chip_balance SET DEFAULT 5000000;

UPDATE users SET chip_balance = 5000000;
