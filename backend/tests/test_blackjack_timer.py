"""
test_blackjack_timer.py — per-player move timer for multiplayer blackjack.

The current actor = the lowest-seat `active` hand; only it carries a non-null
`move_deadline_at`. On expiry the server auto-STANDS the player (the only
chip-safe default — an auto-hit could bust them) and advances the turn.
Enforcement is lazy: the next /state poll or /action resolves it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


@pytest_asyncio.fixture
async def multi(db):
    """An AsyncClient + an `as_user(uid)` switch sharing one db session."""
    from backend.auth import get_current_user  # noqa: PLC0415
    from backend.database import get_db  # noqa: PLC0415
    from backend.main import app  # noqa: PLC0415

    holder = {"uid": TEST_USER_ID}

    async def _override_user():
        return holder["uid"]

    async def _override_db():
        yield db

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    def as_user(uid) -> None:
        holder["uid"] = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, as_user

    app.dependency_overrides.clear()


# ─── helpers ──────────────────────────────────────────────────────────────────


async def _seed_seat(db, table_id, user_id, seat_number):
    from backend.models import TableSeat  # noqa: PLC0415

    seat = TableSeat(
        id=uuid.uuid4(),
        table_id=table_id,
        user_id=user_id,
        seat_number=seat_number,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.flush()
    return seat


async def _hand_by_user(db, session_id, user_id):
    from backend.models import Hand  # noqa: PLC0415

    return (await db.execute(
        select(Hand).where(Hand.session_id == session_id, Hand.user_id == user_id)
    )).scalar_one()


def _card(value: str, suit: str = "spades") -> dict:
    return {"suit": suit, "value": value}


# ─── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deal_sets_move_deadline_and_state_exposes_it(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "alice")
    as_user(TEST_USER_ID)
    r = await ac.post("/api/tables", json={"name": "T", "min_bet": 500, "max_bet": 50_000})
    assert r.status_code == 200, r.text
    table_id = r.json()["id"]
    await ac.post(f"/api/tables/{table_id}/join")
    r = await ac.post(f"/api/tables/{table_id}/deal", json={"bet": 1_000})
    assert r.status_code == 200, r.text

    st = (await ac.get(f"/api/tables/{table_id}/state")).json()
    hand = st["hands"][0]
    assert "move_deadline_at" in hand
    # A fresh deal puts the lone player on the clock (unless they were dealt a
    # natural blackjack, which is already terminal).
    if hand["status"] == "active":
        assert hand["move_deadline_at"] is not None
        deadline = datetime.fromisoformat(hand["move_deadline_at"])
        delta = (deadline - datetime.now(timezone.utc)).total_seconds()
        assert 20 <= delta <= 31


@pytest.mark.asyncio
async def test_stamp_sets_deadline_only_on_current_actor(db):
    from backend.game.blackjack import state as gs  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "alice")
    await seed_user(db, OTHER_USER_ID, "bob")
    table = await seed_table(db)
    await _seed_seat(db, table.id, TEST_USER_ID, 1)
    await _seed_seat(db, table.id, OTHER_USER_ID, 2)
    session = await seed_session(db, table.id, status="playing")
    await seed_hand(db, session.id, TEST_USER_ID, cards=[_card("10"), _card("6")], status="active")
    await seed_hand(db, session.id, OTHER_USER_ID, cards=[_card("10"), _card("5")], status="active")

    await gs.stamp_current_deadline(session.id, db)

    h1 = await _hand_by_user(db, session.id, TEST_USER_ID)  # seat 1 → current actor
    h2 = await _hand_by_user(db, session.id, OTHER_USER_ID)  # seat 2 → waiting
    assert h1.move_deadline_at is not None
    assert h2.move_deadline_at is None


@pytest.mark.asyncio
async def test_expired_deadline_auto_stands_current_actor(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "alice")
    await seed_user(db, OTHER_USER_ID, "bob")
    table = await seed_table(db)
    await _seed_seat(db, table.id, TEST_USER_ID, 1)
    await _seed_seat(db, table.id, OTHER_USER_ID, 2)
    session = await seed_session(
        db, table.id, status="playing",
        dealer_cards=[_card("6", "hearts"), _card("10", "clubs")],
        deck_state=[_card("5") for _ in range(10)],
    )
    await seed_hand(db, session.id, TEST_USER_ID, cards=[_card("10"), _card("6")], status="active")
    await seed_hand(db, session.id, OTHER_USER_ID, cards=[_card("10", "diamonds"), _card("5")], status="active")

    h1 = await _hand_by_user(db, session.id, TEST_USER_ID)
    h2 = await _hand_by_user(db, session.id, OTHER_USER_ID)
    h1.move_deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)  # seat-1 actor expired
    h2.move_deadline_at = None
    await db.flush()

    # Another player polling resolves the abandoned turn.
    as_user(OTHER_USER_ID)
    r = await ac.get(f"/api/tables/{table.id}/state")
    assert r.status_code == 200, r.text

    h1b = await _hand_by_user(db, session.id, TEST_USER_ID)
    h2b = await _hand_by_user(db, session.id, OTHER_USER_ID)
    assert h1b.status == "standing"             # auto-stood, not hit
    assert h1b.cards == [_card("10"), _card("6")]  # cards untouched (chip-safe)
    assert h1b.move_deadline_at is None
    assert h2b.move_deadline_at is not None      # turn passed to seat 2


@pytest.mark.asyncio
async def test_hit_refreshes_the_deadline(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "alice")
    table = await seed_table(db)
    await _seed_seat(db, table.id, TEST_USER_ID, 1)
    session = await seed_session(
        db, table.id, status="playing",
        dealer_cards=[_card("6", "hearts"), _card("10", "clubs")],
        deck_state=[_card("3") for _ in range(10)],
    )
    h = await seed_hand(db, session.id, TEST_USER_ID, cards=[_card("2"), _card("4")], status="active")
    # A near deadline that is NOT yet expired, so the hit is processed (not auto-resolved).
    h.move_deadline_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db.flush()

    as_user(TEST_USER_ID)
    r = await ac.post(f"/api/tables/{table.id}/action", json={"action": "hit"})
    assert r.status_code == 200, r.text

    hb = await _hand_by_user(db, session.id, TEST_USER_ID)
    assert hb.status == "active"  # 2 + 4 + 3 = 9, still the player's decision
    # The clock reset from ~5s to a fresh ~30s window.
    assert hb.move_deadline_at is not None
    assert (hb.move_deadline_at - datetime.now(timezone.utc)).total_seconds() > 20


@pytest.mark.asyncio
async def test_advance_to_dealer_turn_clears_deadline(db):
    from backend.game.blackjack import state as gs  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "alice")
    table = await seed_table(db)
    await _seed_seat(db, table.id, TEST_USER_ID, 1)
    session = await seed_session(
        db, table.id, status="playing",
        dealer_cards=[_card("K", "hearts"), _card("7", "clubs")],
        deck_state=[_card("5") for _ in range(10)],
    )
    h = await seed_hand(db, session.id, TEST_USER_ID, cards=[_card("10"), _card("9")], status="standing")
    h.move_deadline_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    await db.flush()

    # No active hands remain → advance triggers the dealer turn; nobody is on the clock.
    await gs.advance_turn(session.id, db)

    hb = await _hand_by_user(db, session.id, TEST_USER_ID)
    assert hb.move_deadline_at is None
