"""migrate.py — apply pending SQL migrations to the configured database.

Runs at container startup (before uvicorn) so a deploy that ships a new
backend/migrations/NNN_*.sql file applies it automatically. Before this
existed, migrations had to be run by hand via `railway run` and were
routinely forgotten — the poker tables shipped in code but 500'd in prod
for days because their DDL was never applied.

Design:
  - Discovers backend/migrations/*.sql in lexicographic (numeric-prefix) order.
  - Records applied files in a `schema_migrations` ledger so each runs once.
  - Splits each file into individual statements (asyncpg can't run multiple
    commands in one prepared statement), while respecting $$-dollar-quoted
    blocks (e.g. the DO $$ ... $$ guard in 005_study.sql) so their inner
    semicolons don't split the statement.
  - Each file is applied inside ONE transaction; on error it rolls back,
    logs which file/statement failed, and exits non-zero so the deploy
    fails loudly instead of booting a half-migrated app.
  - Idempotent regardless of the ledger too: the migration files all use
    CREATE TABLE/INDEX IF NOT EXISTS + ADD COLUMN IF NOT EXISTS guards.

Usage:
    python -m backend.migrate            # apply pending, exit 0 on success
    python -m backend.migrate --dry-run  # list pending files, apply nothing
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import sys

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger("betwise.migrate")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"

_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements on top-level semicolons,
    treating $$-dollar-quoted regions as opaque (their semicolons don't split).

    Handles the `DO $$ BEGIN ... END $$;` block in 005_study.sql correctly.
    Line comments (-- ...) are stripped; statements that are empty after
    stripping are dropped.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False  # inside a $$ ... $$ region

    # Strip full-line comments first (keeps inline simple; our SQL has none mid-statement).
    cleaned_lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)

    i = 0
    while i < len(cleaned):
        # Detect a $$ delimiter (dollar-quote with no tag, which is all this repo uses).
        if cleaned[i : i + 2] == "$$":
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = cleaned[i]
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _migration_files() -> list[pathlib.Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))


async def _applied_set(conn) -> set[str]:
    rows = (await conn.execute(text("SELECT filename FROM schema_migrations"))).scalars().all()
    return set(rows)


async def run_migrations(dry_run: bool = False) -> int:
    import os  # noqa: PLC0415

    # No real database configured (e.g. a health-only boot, or local `docker run`
    # without DATABASE_URL): skip silently so the app can still start. We only
    # auto-migrate when pointed at a real DATABASE_URL/BETWISE_TEST_DB_URL.
    if not (os.environ.get("DATABASE_URL") or os.environ.get("BETWISE_TEST_DB_URL")):
        logger.info("migrate: no DATABASE_URL/BETWISE_TEST_DB_URL set — skipping (nothing to migrate).")
        return 0

    engine = get_engine()
    files = _migration_files()
    if not files:
        logger.info("migrate: no migration files found at %s", MIGRATIONS_DIR)
        return 0

    # Ensure the ledger exists.
    async with engine.begin() as conn:
        await conn.execute(text(_LEDGER_DDL))

    async with engine.connect() as conn:
        applied = await _applied_set(conn)

    pending = [f for f in files if f.name not in applied]
    if not pending:
        logger.info("migrate: schema up to date (%d migrations already applied)", len(applied))
        return 0

    logger.info("migrate: %d pending migration(s): %s", len(pending), ", ".join(p.name for p in pending))
    if dry_run:
        for p in pending:
            print(f"PENDING {p.name}")
        return 0

    for path in pending:
        sql = path.read_text(encoding="utf-8")
        statements = _split_statements(sql)
        try:
            async with engine.begin() as conn:
                for stmt in statements:
                    await conn.execute(text(stmt))
                await conn.execute(
                    text("INSERT INTO schema_migrations (filename) VALUES (:f) "
                         "ON CONFLICT (filename) DO NOTHING"),
                    {"f": path.name},
                )
            logger.info("migrate: applied %s (%d statements)", path.name, len(statements))
        except Exception:
            logger.exception("migrate: FAILED applying %s — rolling back and aborting deploy", path.name)
            await engine.dispose()
            return 1

    await engine.dispose()
    logger.info("migrate: done.")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    dry = "--dry-run" in sys.argv
    return asyncio.run(run_migrations(dry_run=dry))


if __name__ == "__main__":
    raise SystemExit(main())
