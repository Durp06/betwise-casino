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


def _is_local_postgres(url: str) -> bool:
    """Cheap heuristic: does the URL point at a local Postgres host?"""
    return ("@localhost" in url) or ("@127.0.0.1" in url) or ("@db:" in url)


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
        # Strip query params that asyncpg doesn't understand (sslmode=, pgbouncer=…)
        # — these come from psycopg2-style URLs people often paste from Supabase docs.
        if "+asyncpg" in url and "?" in url:
            url = url.split("?", 1)[0]

        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        elif "+asyncpg" in url and not _is_local_postgres(url):
            # Defensive URL normalization for Supabase + asyncpg quirks.
            from sqlalchemy.engine.url import make_url  # noqa: PLC0415

            parsed = make_url(url)

            # 1. Missing database name → asyncpg falls back to using the
            #    username as the db name, which on Supabase looks like
            #    "postgres.<project-ref>" and produces InvalidCatalogNameError.
            #    Supabase's default database is always literally "postgres".
            if not parsed.database:
                parsed = parsed.set(database="postgres")

            # 2. asyncpg + dotted username (Supabase pooler uses
            #    `postgres.<project-ref>`): some asyncpg versions misinterpret
            #    the dot when reading from the URL. Pass user/password via
            #    connect_args instead, which asyncpg.connect() consumes
            #    directly as kwargs without re-parsing.
            if parsed.username and "." in parsed.username:
                connect_args["user"] = parsed.username
                if parsed.password:
                    connect_args["password"] = parsed.password
                parsed = parsed.set(username=None, password=None)

            url = str(parsed)

            # Supabase / managed Postgres require SSL. "require" = encrypt
            # but don't verify the certificate chain.
            connect_args["ssl"] = "require"
            # Port 5432 (session mode) supports prepared statements, but
            # disabling the cache keeps us safe if someone accidentally
            # points at 6543 (txn mode / pgbouncer), which doesn't.
            connect_args["statement_cache_size"] = 0

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
    """FastAPI dependency — yields an AsyncSession, commits on success, rolls back on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
