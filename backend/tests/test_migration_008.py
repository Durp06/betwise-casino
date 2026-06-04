"""
test_migration_008.py — AC-B7, AC-B8, AC-B9.

Tests map 1:1 to acceptance criteria from specs/centralized-money-system.md §3
(Backend section).  All tests are EXPECTED to fail (red) until the implementation
creates backend/migrations/008_centralize_starting_balance.sql.

SQLite compatibility note (spec §5, §7):
  ALTER TABLE ... ALTER COLUMN ... SET DEFAULT is Postgres-only syntax and is NOT
  executable on the SQLite in-memory test engine.  The migration test therefore:
    - Asserts the ALTER statement's shape TEXTUALLY via _split_statements (AC-B7, AC-B8).
    - Tests the UPDATE semantics by EXECUTING only the UPDATE statement against
      the SQLite in-memory DB (AC-B9).
  This keeps the test green on SQLite once the migration file exists, while still
  proving both statements are present and correctly shaped for production Postgres.
"""

from __future__ import annotations

import pathlib
import re
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


# ─── path constant ────────────────────────────────────────────────────────────

_MIGRATION_PATH = (
    pathlib.Path(__file__).parent.parent / "migrations" / "008_centralize_starting_balance.sql"
)


# ─── AC-B7 + AC-B8: file exists and _split_statements returns both statements ─

def test_migration_file_exists_and_has_two_statements() -> None:
    """AC-B7 + AC-B8: The migration file exists and _split_statements returns exactly
    two distinct statements — one ALTER ... SET DEFAULT and one UPDATE users SET
    chip_balance — neither merged nor dropped.
    """
    from backend.migrate import _split_statements  # noqa: PLC0415

    assert _MIGRATION_PATH.exists(), (
        f"Migration file not found: {_MIGRATION_PATH}\n"
        "Task 4 must create backend/migrations/008_centralize_starting_balance.sql"
    )

    sql_text = _MIGRATION_PATH.read_text(encoding="utf-8")
    statements = _split_statements(sql_text)

    assert len(statements) == 2, (
        f"expected exactly 2 statements from _split_statements, got {len(statements)}: {statements}"
    )

    # Normalise for case-insensitive substring matching
    normalised = [re.sub(r"\s+", " ", s).strip().lower() for s in statements]

    # AC-B7(a) — must contain an ALTER TABLE ... SET DEFAULT statement
    alter_stmts = [s for s in normalised if "alter table" in s and "set default" in s]
    assert alter_stmts, (
        "No ALTER TABLE ... SET DEFAULT statement found among the split statements.\n"
        f"Statements after split: {statements}"
    )

    # AC-B7(b) — must contain an UPDATE users SET chip_balance statement
    update_stmts = [s for s in normalised if "update users" in s and "chip_balance" in s]
    assert update_stmts, (
        "No UPDATE users SET chip_balance statement found among the split statements.\n"
        f"Statements after split: {statements}"
    )

    # AC-B8 — they must be DISTINCT entries (not merged into one)
    assert alter_stmts != update_stmts, (
        "ALTER and UPDATE appear to be the same statement — they must be distinct"
    )

    # The two statements found above must be different entries in the list
    alter_indices  = [i for i, s in enumerate(normalised) if "alter table" in s and "set default" in s]
    update_indices = [i for i, s in enumerate(normalised) if "update users" in s and "chip_balance" in s]
    assert set(alter_indices).isdisjoint(set(update_indices)), (
        "ALTER and UPDATE share the same statement index — they must be separate entries"
    )


# ─── AC-B9: UPDATE resets all pre-existing user balances to 5_000_000 ─────────

@pytest.mark.asyncio
async def test_migration_resets_all_users() -> None:
    """AC-B9: After executing the migration's UPDATE statement against the test DB,
    every user row has chip_balance == 5_000_000.

    We do NOT execute the ALTER statement (Postgres-only syntax, incompatible with
    SQLite).  Its shape is already verified textually in the test above.  This test
    exercises the UPDATE's row-level semantics against the real in-memory SQLite
    engine used by the test suite.
    """
    from backend.migrate import _split_statements  # noqa: PLC0415
    from backend.models import Base, User  # noqa: PLC0415

    assert _MIGRATION_PATH.exists(), (
        f"Migration file not found: {_MIGRATION_PATH}\n"
        "Task 4 must create backend/migrations/008_centralize_starting_balance.sql"
    )

    # Build a standalone in-memory SQLite engine with the ORM schema.
    # We use a separate engine (not the session-scoped test engine) so this test
    # is fully self-contained and doesn't pollute the shared fixture DB.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # Seed several users with MIXED balances (deliberately not 5_000_000)
    mixed_balances = [0, 500, 1000, 100_000, 3_500_000]
    async with factory() as session:
        for i, bal in enumerate(mixed_balances):
            session.add(
                User(
                    id=uuid.uuid4(),
                    username=f"migtest_user_{i}",
                    chip_balance=bal,
                    total_hands=0,
                    correct_decisions=0,
                    current_streak=0,
                    best_streak=0,
                    created_at=datetime.now(timezone.utc),
                )
            )
        await session.commit()

    # Extract only the UPDATE statement from the migration file and execute it.
    # The ALTER is intentionally skipped — SQLite cannot run it.
    sql_text = _MIGRATION_PATH.read_text(encoding="utf-8")
    statements = _split_statements(sql_text)

    normalised = [re.sub(r"\s+", " ", s).strip().lower() for s in statements]
    update_stmts = [
        orig for orig, norm in zip(statements, normalised, strict=True)
        if "update users" in norm and "chip_balance" in norm
    ]
    assert update_stmts, "Could not find the UPDATE statement in the migration file"

    update_sql = update_stmts[0]

    async with engine.begin() as conn:
        await conn.execute(text(update_sql))

    # Assert every user now has chip_balance == 5_000_000
    async with factory() as session:
        from sqlalchemy import select  # noqa: PLC0415

        rows = (await session.execute(select(User))).scalars().all()

    assert rows, "Expected at least one user row after seeding"
    for row in rows:
        assert row.chip_balance == 5_000_000, (
            f"user {row.username} has chip_balance={row.chip_balance} after migration UPDATE; "
            "expected 5_000_000"
        )

    await engine.dispose()
