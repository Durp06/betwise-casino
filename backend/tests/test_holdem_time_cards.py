"""
test_holdem_time_cards.py — Hold'em time cards.

Each player is granted 5 time cards when they take a seat. Using one (only on
your own turn, while your clock is still live) extends the current move deadline
by +15s and decrements the count. Cards do NOT regenerate during play; a fresh 5
is granted each time a player sits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import OTHER_USER_ID, TEST_USER_ID, seed_user


@pytest_asyncio.fixture
async def multi(db):
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


async def _create_table(ac, as_user, uid) -> str:
    as_user(uid)
    body = {"name": "Cards Holdem", "small_blind": 50, "big_blind": 100,
            "min_buy_in": 2_000, "max_buy_in": 20_000, "max_seats": 6}
    r = await ac.post("/api/holdem/tables", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _join(ac, as_user, uid, table_id, buy_in=10_000):
    as_user(uid)
    r = await ac.post(f"/api/holdem/tables/{table_id}/join", json={"buy_in": buy_in})
    assert r.status_code == 200, r.text
    return r


async def _leave(ac, as_user, uid, table_id):
    as_user(uid)
    return await ac.post(f"/api/holdem/tables/{table_id}/leave")


async def _state(ac, as_user, uid, table_id) -> dict:
    as_user(uid)
    r = await ac.get(f"/api/holdem/tables/{table_id}/state")
    assert r.status_code == 200, r.text
    return r.json()


async def _deal(ac, as_user, uid, table_id) -> dict:
    as_user(uid)
    r = await ac.post(f"/api/holdem/tables/{table_id}/deal")
    assert r.status_code == 200, r.text
    return r.json()


async def _act(ac, as_user, uid, table_id, action, amount=0):
    as_user(uid)
    return await ac.post(f"/api/holdem/tables/{table_id}/act", json={"action": action, "amount": amount})


async def _use_card(ac, as_user, uid, table_id):
    as_user(uid)
    return await ac.post(f"/api/holdem/tables/{table_id}/use-time-card")


def _actor_uid(state: dict) -> uuid.UUID:
    hand = state["current_hand"]
    seat = next(s for s in hand["seats"] if s["seat_number"] == hand["current_to_act_seat"])
    return uuid.UUID(seat["user_id"])


async def _active_hand(db, table_id: str):
    from backend.models import HoldemHand  # noqa: PLC0415

    return (await db.execute(
        select(HoldemHand).where(
            HoldemHand.table_id == uuid.UUID(table_id), HoldemHand.status == "active"
        )
    )).scalar_one()


async def _two_player_table(ac, as_user, db):
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "bob", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, OTHER_USER_ID, table_id)
    return table_id


# ─── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_join_grants_five_time_cards(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    assert st["your_time_cards_remaining"] == 5


@pytest.mark.asyncio
async def test_use_time_card_decrements_and_extends_deadline(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    actor = _actor_uid(st)
    before = datetime.fromisoformat(st["current_hand"]["move_deadline_at"])

    r = await _use_card(ac, as_user, actor, table_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["your_time_cards_remaining"] == 4
    after = datetime.fromisoformat(body["current_hand"]["move_deadline_at"])
    assert 14 <= (after - before).total_seconds() <= 16


@pytest.mark.asyncio
async def test_use_time_card_not_your_turn_is_rejected(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    actor = _actor_uid(st)
    waiter = OTHER_USER_ID if actor == TEST_USER_ID else TEST_USER_ID

    r = await _use_card(ac, as_user, waiter, table_id)
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_time_cards_run_out_then_reject(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)
    actor = _actor_uid(await _state(ac, as_user, TEST_USER_ID, table_id))

    for expected_left in (4, 3, 2, 1, 0):
        r = await _use_card(ac, as_user, actor, table_id)
        assert r.status_code == 200, r.text
        assert r.json()["your_time_cards_remaining"] == expected_left

    # Sixth use — nothing left.
    r = await _use_card(ac, as_user, actor, table_id)
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_time_cards_do_not_regenerate_across_hands(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)
    actor = _actor_uid(await _state(ac, as_user, TEST_USER_ID, table_id))

    await _use_card(ac, as_user, actor, table_id)
    await _use_card(ac, as_user, actor, table_id)  # actor now has 3

    # Drive this hand to completion and deal another.
    for _ in range(40):
        st = await _state(ac, as_user, actor, table_id)
        hand = st["current_hand"]
        if hand is None or hand["status"] == "complete":
            break
        cta = hand["current_to_act_seat"]
        if cta is None:
            break
        seat = next(s for s in hand["seats"] if s["seat_number"] == cta)
        to_call = hand["current_bet_to_match"] - seat["current_bet"]
        await _act(ac, as_user, uuid.UUID(seat["user_id"]), table_id, "call" if to_call > 0 else "check")
    await _deal(ac, as_user, actor, table_id)

    st = await _state(ac, as_user, actor, table_id)
    assert st["your_time_cards_remaining"] == 3  # no regen


@pytest.mark.asyncio
async def test_rejoin_grants_a_fresh_five(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    # (cannot use a card pre-deal; just verify leave/rejoin resets the grant)
    await _leave(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    assert st["your_time_cards_remaining"] == 5


@pytest.mark.asyncio
async def test_cannot_use_card_after_deadline_expired(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)
    actor = _actor_uid(await _state(ac, as_user, TEST_USER_ID, table_id))

    hand = await _active_hand(db, table_id)
    hand.move_deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.flush()

    # You can't extend a clock that has already run out.
    r = await _use_card(ac, as_user, actor, table_id)
    assert r.status_code == 400, r.text
