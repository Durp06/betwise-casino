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

@pytest_asyncio.fixture(scope="function")
async def engine():
    """**Function-scoped** async engine — fresh in-memory DB per test.

    Round-7 isolation fix: session-scoped engine + StaticPool shared the
    same in-memory DB across all tests, which leaked across the boundary in
    spite of the `db` fixture's rollback (router tests that drive the FastAPI
    app commit through `get_db`'s session-level commit, and the persistent
    fortune_pool singleton row meant tests that mutated the pool could leave
    observable state for the next test). Going function-scoped eliminates
    the entire class — each test gets a clean schema + a freshly-seeded
    fortune_pool row.

    Cost: each test re-runs `create_all` + the seed INSERT. On in-memory
    SQLite this is fast (~milliseconds) and the determinism is worth it.

    NOTE: this seed is the test-only equivalent of the `INSERT ... ON CONFLICT`
    in `migrations/005_pai_gow.sql`. The SQL migration is NOT run by CI or
    any automated process — it's applied manually to prod Supabase. Tests
    use `Base.metadata.create_all` for the schema and this fixture's INSERT
    for the singleton row.
    """
    from sqlalchemy import insert  # noqa: PLC0415
    from backend.models import Base, FortunePool, FORTUNE_POOL_SINGLETON_ID  # noqa: PLC0415

    test_url = os.environ["BETWISE_TEST_DB_URL"]
    _engine = create_async_engine(
        test_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Seed the fortune_pool singleton.
        await conn.execute(
            insert(FortunePool).values(
                id=FORTUNE_POOL_SINGLETON_ID,
                amount_cents=100_000,
                seed_cents=100_000,
                last_updated_at=datetime.now(timezone.utc),
            )
        )
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


# ─── Pai Gow seed helpers (round-6 architectural shift — own container) ──────

async def seed_pai_gow_table(
    db: AsyncSession,
    name: str = "Test PG Table",
    min_bet_cents: int = 500,
    max_bet_cents: int = 50_000,
    min_fortune_bet_cents: int = 100,
    max_fortune_bet_cents: int = 10_000,
    max_seats: int = 3,
) -> "backend.models.PaiGowTable":  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import PaiGowTable  # noqa: PLC0415

    table = PaiGowTable(
        id=_uuid.uuid4(),
        name=name,
        min_bet_cents=min_bet_cents,
        max_bet_cents=max_bet_cents,
        min_fortune_bet_cents=min_fortune_bet_cents,
        max_fortune_bet_cents=max_fortune_bet_cents,
        max_seats=max_seats,
        created_at=datetime.now(timezone.utc),
    )
    db.add(table)
    await db.commit()
    await db.refresh(table)
    return table


async def seed_pai_gow_seat(
    db: AsyncSession,
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    seat_number: int = 1,
) -> "backend.models.PaiGowSeat":  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import PaiGowSeat  # noqa: PLC0415

    seat = PaiGowSeat(
        id=_uuid.uuid4(),
        table_id=table_id,
        user_id=user_id,
        seat_number=seat_number,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.commit()
    await db.refresh(seat)
    return seat


async def seed_pai_gow_round(
    db: AsyncSession,
    table_id: uuid.UUID,
    round_number: int = 1,
    status: str = "betting",
    dealer_dealt_cards: list | None = None,
    deck_state: list | None = None,
    playing_started_at=None,
) -> "backend.models.PaiGowRound":  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import PaiGowRound  # noqa: PLC0415

    rnd = PaiGowRound(
        id=_uuid.uuid4(),
        table_id=table_id,
        round_number=round_number,
        dealer_dealt_cards=dealer_dealt_cards if dealer_dealt_cards is not None else [],
        deck_state=deck_state if deck_state is not None else [],
        status=status,
        playing_started_at=playing_started_at,
        created_at=datetime.now(timezone.utc),
    )
    db.add(rnd)
    await db.commit()
    await db.refresh(rnd)
    return rnd


async def seed_pai_gow_player_hand(
    db: AsyncSession,
    round_id: uuid.UUID,
    user_id: uuid.UUID,
    dealt_cards: list | None = None,
    bet_cents: int = 1_000,
    fortune_bet_cents: int = 0,
    action_status: str = "dealt",
) -> "backend.models.PaiGowPlayerHand":  # type: ignore[name-defined]
    import uuid as _uuid  # noqa: PLC0415
    from backend.models import PaiGowPlayerHand  # noqa: PLC0415

    if dealt_cards is None:
        dealt_cards = [
            {"suit": "hearts", "value": "A"},
            {"suit": "hearts", "value": "K"},
            {"suit": "hearts", "value": "Q"},
            {"suit": "spades", "value": "J"},
            {"suit": "diamonds", "value": "10"},
            {"suit": "clubs", "value": "9"},
            {"suit": "clubs", "value": "2"},
        ]
    hand = PaiGowPlayerHand(
        id=_uuid.uuid4(),
        round_id=round_id,
        user_id=user_id,
        dealt_cards=dealt_cards,
        bet_cents=bet_cents,
        fortune_bet_cents=fortune_bet_cents,
        action_status=action_status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    await db.commit()
    await db.refresh(hand)
    return hand


async def seed_pai_gow_streak(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_streak: int = 0,
    longest_streak: int = 0,
    total_optimal: int = 0,
    total_played: int = 0,
) -> "backend.models.PaiGowStrategyStreak":  # type: ignore[name-defined]
    from backend.models import PaiGowStrategyStreak  # noqa: PLC0415

    streak = PaiGowStrategyStreak(
        user_id=user_id,
        current_streak=current_streak,
        longest_streak=longest_streak,
        total_optimal=total_optimal,
        total_played=total_played,
        last_played_at=None,
    )
    db.add(streak)
    await db.commit()
    await db.refresh(streak)
    return streak


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
