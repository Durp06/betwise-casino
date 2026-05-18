"""
conftest.py — shared fixtures for the BetWise Casino test suite.

Design constraints (from specs/betwise-casino.md §7 + §10):
- Use aiosqlite in-memory SQLite so tests never touch Postgres.
- ORM `Base.metadata.create_all` builds the schema (not the SQL migration file,
  which uses Postgres-only syntax).  The SQL file is exercised by the CI Postgres
  job only.
- `get_current_user` is overridden via FastAPI's dependency-override mechanism
  so no real JWT is needed.
- Anthropic client is patched so no test ever hits the real Anthropic API.
- `BETWISE_DEV_USER_ID` env var is set to TEST_USER_ID so auth.py's bypass path
  is active throughout tests.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# ─── deterministic IDs used across all tests ─────────────────────────────────
TEST_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_USER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

# Tell auth.py to bypass JWT for all tests
os.environ.setdefault("BETWISE_DEV_USER_ID", str(TEST_USER_ID))
# Point the engine at an in-memory SQLite database for all tests
os.environ.setdefault("BETWISE_TEST_DB_URL", "sqlite+aiosqlite:///:memory:")


# ─── async engine + session ───────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def engine():
    """Session-scoped async engine backed by in-memory SQLite."""
    from backend.models import Base  # noqa: PLC0415  (import after env is set)

    test_url = os.environ["BETWISE_TEST_DB_URL"]
    _engine = create_async_engine(
        test_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test async session that rolls back after the test."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ─── FastAPI app + HTTP clients ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the FastAPI app with TEST_USER_ID as current user."""
    from backend.main import app  # noqa: PLC0415
    from backend.auth import get_current_user  # noqa: PLC0415
    from backend.database import get_db  # noqa: PLC0415

    async def _override_user():
        return TEST_USER_ID

    async def _override_db():
        yield db

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def other_client(db) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient authenticated as OTHER_USER_ID (different from TEST_USER_ID)."""
    from backend.main import app  # noqa: PLC0415
    from backend.auth import get_current_user  # noqa: PLC0415
    from backend.database import get_db  # noqa: PLC0415

    async def _override_user():
        return OTHER_USER_ID

    async def _override_db():
        yield db

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ─── seed helpers ────────────────────────────────────────────────────────────

async def seed_user(db: AsyncSession, user_id: uuid.UUID, username: str, chip_balance: int = 100_000) -> "backend.models.User":  # type: ignore[name-defined]
    from backend.models import User  # noqa: PLC0415

    user = User(
        id=user_id,
        username=username,
        chip_balance=chip_balance,
        total_hands=0,
        correct_decisions=0,
        current_streak=0,
        best_streak=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def seed_table(
    db: AsyncSession,
    name: str = "Test Table",
    min_bet: int = 500,
    max_bet: int = 50_000,
    max_seats: int = 3,
    status: str = "waiting",
) -> "backend.models.CasinoTable":  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import CasinoTable  # noqa: PLC0415

    table = CasinoTable(
        id=_uuid.uuid4(),
        name=name,
        min_bet=min_bet,
        max_bet=max_bet,
        max_seats=max_seats,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(table)
    await db.commit()
    await db.refresh(table)
    return table


async def seed_session(
    db: AsyncSession,
    table_id: uuid.UUID,
    status: str = "playing",
    dealer_cards: list = None,
    deck_state: list = None,
) -> "backend.models.GameSession":  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import GameSession  # noqa: PLC0415

    session = GameSession(
        id=_uuid.uuid4(),
        table_id=table_id,
        game_type="blackjack",
        dealer_cards=dealer_cards or [{"suit": "hearts", "value": "6"}],
        deck_state=deck_state or [],
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def seed_hand(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    cards: list = None,
    bet: int = 1_000,
    status: str = "active",
) -> "backend.models.Hand":  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import Hand  # noqa: PLC0415

    hand = Hand(
        id=_uuid.uuid4(),
        session_id=session_id,
        user_id=user_id,
        cards=cards or [{"suit": "hearts", "value": "8"}, {"suit": "spades", "value": "8"}],
        bet=bet,
        status=status,
        outcome=None,
        payout=None,
    )
    db.add(hand)
    await db.commit()
    await db.refresh(hand)
    return hand


async def seed_actions(
    db: AsyncSession,
    hand_id: uuid.UUID,
    user_id: uuid.UUID,
    rows: list[dict],
) -> list["backend.models.PlayerAction"]:  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import PlayerAction  # noqa: PLC0415

    actions = []
    for i, row in enumerate(rows):
        action = PlayerAction(
            id=_uuid.uuid4(),
            hand_id=hand_id,
            user_id=user_id,
            action=row.get("action", "hit"),
            player_guess=row.get("player_guess", "hit"),
            optimal_action=row.get("optimal_action", "hit"),
            was_correct=row.get("was_correct", True),
            hand_snapshot=row.get("hand_snapshot", [{"suit": "hearts", "value": "8"}]),
            dealer_upcard=row.get("dealer_upcard", {"suit": "clubs", "value": "10"}),
            chipy_explanation=row.get("chipy_explanation", None),
            created_at=datetime.now(timezone.utc),
        )
        db.add(action)
        actions.append(action)
    await db.commit()
    return actions


# ─── Anthropic mock ───────────────────────────────────────────────────────────

class _FakeStream:
    """Minimal async context manager that yields a few text chunks then stops."""

    class _FakeTextEvent:
        def __init__(self, text: str):
            self.type = "content_block_delta"
            self.delta = type("D", (), {"type": "text_delta", "text": text})()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def __aiter__(self):
        for chunk in ["Great move! ", "You're on the right track."]:
            yield self._FakeTextEvent(chunk)

    async def get_final_message(self):
        return type("M", (), {"content": [type("B", (), {"text": "Great move! You're on the right track."})()]})()


@pytest.fixture
def mock_anthropic(mocker):
    """Patch anthropic.AsyncAnthropic so no test hits the real API."""
    fake_stream = _FakeStream()
    mock = mocker.patch("anthropic.AsyncAnthropic")
    instance = mock.return_value
    instance.messages.stream.return_value = fake_stream
    return mock
