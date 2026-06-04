"""
test_database_guard.py — get_engine() must refuse the in-memory SQLite
fallback in production rather than silently booting a throwaway DB.

If DATABASE_URL is unset in production (e.g. a Railway misconfig), the app
must crash loudly at engine creation instead of serving a working-looking
app backed by an ephemeral SQLite that loses all data on every restart and
enforces none of the real Postgres constraints. The guard is SQLite-specific:
a real Postgres URL in production must still boot.
"""
from __future__ import annotations

import asyncio

import pytest

import backend.database as database
import backend.migrate as migrate


def test_production_without_database_url_refuses_sqlite(monkeypatch):
    """ENVIRONMENT=production + no DATABASE_URL → RuntimeError, not a SQLite fallback."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BETWISE_TEST_DB_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Force a fresh engine build (the module caches a singleton).
    monkeypatch.setattr(database, "_engine", None)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database.get_engine()

    # The guard must fire BEFORE an engine is cached, so nothing leaks.
    assert database._engine is None


def test_non_production_allows_sqlite_fallback(monkeypatch):
    """No ENVIRONMENT (the test/CI path) → the in-memory SQLite fallback is allowed."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BETWISE_TEST_DB_URL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setattr(database, "_engine", None)

    engine = database.get_engine()
    assert engine is not None
    assert engine.url.drivername.startswith("sqlite")


def test_production_with_postgres_url_is_allowed(monkeypatch):
    """The guard is SQLite-specific: a real Postgres URL boots fine in production.

    Pins against an over-broad regression like `if ENVIRONMENT == "production":
    raise`, which would take down a correctly-configured prod deploy.
    """
    monkeypatch.delenv("BETWISE_TEST_DB_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://u:p@db.example.com:5432/postgres"
    )
    monkeypatch.setattr(database, "_engine", None)

    engine = database.get_engine()  # builds lazily; does not open a connection
    assert engine is not None
    assert "asyncpg" in engine.url.drivername


def test_migrate_refuses_production_without_database_url(monkeypatch):
    """The boot-time migration step fails loudly in production with no DATABASE_URL,
    so the deploy aborts before uvicorn starts instead of serving a throwaway DB."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BETWISE_TEST_DB_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        asyncio.run(migrate.run_migrations())

