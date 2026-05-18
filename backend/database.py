"""
database.py — async SQLAlchemy engine + sessionmaker for BetWise Casino.

Design constraints (specs/betwise-casino.md §T2):
- NO module-level engine creation or DB connections.
- get_engine() and get_session_factory() lazily read DATABASE_URL on first call
  and cache the result.
- If BETWISE_TEST_DB_URL is set, it takes precedence over DATABASE_URL.
- get_db() is a FastAPI dependency that yields an AsyncSession and closes it.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# ─── shared declarative base ─────────────────────────────────────────────────
# Models import this, not database.get_engine(), so it's safe at module level.
Base = declarative_base()

# ─── lazy engine + session factory cache ─────────────────────────────────────
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return (and lazily create) the singleton async engine.

    Reads BETWISE_TEST_DB_URL first (for tests), then DATABASE_URL.
    Calling this function twice always returns the same engine instance.
    """
    global _engine
    if _engine is None:
        url = (
            os.environ.get("BETWISE_TEST_DB_URL")
            or os.environ.get("DATABASE_URL")
            or "sqlite+aiosqlite:///:memory:"
        )
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_async_engine(url, connect_args=connect_args)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (and lazily create) the singleton session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an AsyncSession and closes it after the request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
