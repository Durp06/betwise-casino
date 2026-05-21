"""
backend/conftest.py — Backend-level test isolation.

Patches AsyncSession.commit() → flush() for the duration of each test.
This ensures that seed_* helper commits don't permanently write to the
shared in-memory SQLite engine, so each test starts with clean state.

The tests/conftest.py `db` fixture rolls back after each test. For this
rollback to work, no commits must have reached the DB. By making commit()
behave like flush(), all writes are pending (not committed) and the
tests/conftest.py rollback undoes them correctly.

This conftest is at backend/ level, loaded before tests/conftest.py.
The monkeypatch is applied via an autouse fixture that depends on the
`db` session from tests/conftest.py.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(autouse=True)
async def _patch_commit_to_flush(db: AsyncSession, monkeypatch):
    """Replace db.commit() with db.flush() for test isolation.

    All writes (including seed_* helpers that call commit()) are flushed
    to the session's identity map but not committed to the DB. The
    tests/conftest.py db fixture's rollback() at teardown then undoes them.

    This makes all tests independent of each other even with a shared
    session-scoped SQLite engine.
    """
    original_commit = db.commit

    async def _flush_instead_of_commit():
        await db.flush()

    monkeypatch.setattr(db, "commit", _flush_instead_of_commit)
    yield
    # Restore is handled by monkeypatch teardown automatically
