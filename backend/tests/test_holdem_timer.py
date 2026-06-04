"""
test_holdem_timer.py — per-player move timer for multiplayer Hold'em.

A turn stamps an absolute `move_deadline_at` on the active hand; enforcement is
lazy (the next /state poll or /act for the table resolves an expired turn):
- facing a bet  → auto-fold
- facing no bet → auto-check

Invariant under test throughout: `move_deadline_at` is non-null IFF a human is
on the clock (`current_to_act_seat is not None`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import OTHER_USER_ID, TEST_USER_ID, seed_user

THIRD_USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


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


async def _create_table(ac, as_user, uid) -> str:
    as_user(uid)
    body = {"name": "Timer Holdem", "small_blind": 50, "big_blind": 100,
            "min_buy_in": 2_000, "max_buy_in": 20_000, "max_seats": 6}
    r = await ac.post("/api/holdem/tables", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _join(ac, as_user, uid, table_id, buy_in=10_000):
    as_user(uid)
    r = await ac.post(f"/api/holdem/tables/{table_id}/join", json={"buy_in": buy_in})
    assert r.status_code == 200, r.text
    return r


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


def _actor_uid(state: dict) -> uuid.UUID:
    """The user_id of the seat that is currently to act."""
    hand = state["current_hand"]
    cta = hand["current_to_act_seat"]
    seat = next(s for s in hand["seats"] if s["seat_number"] == cta)
    return uuid.UUID(seat["user_id"])


def _actor_to_call(state: dict) -> int:
    hand = state["current_hand"]
    cta = hand["current_to_act_seat"]
    seat = next(s for s in hand["seats"] if s["seat_number"] == cta)
    return hand["current_bet_to_match"] - seat["current_bet"]


async def _active_hand(db, table_id: str):
    from backend.models import HoldemHand  # noqa: PLC0415

    return (await db.execute(
        select(HoldemHand).where(
            HoldemHand.table_id == uuid.UUID(table_id), HoldemHand.status == "active"
        )
    )).scalar_one()


async def _expire_deadline(db, table_id: str) -> None:
    """Push the active hand's move deadline one second into the past."""
    hand = await _active_hand(db, table_id)
    hand.move_deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.flush()


async def _two_player_table(ac, as_user, db):
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "bob", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, OTHER_USER_ID, table_id)
    return table_id


# ─── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deal_sets_move_deadline_on_first_actor(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    hand = st["current_hand"]
    assert hand["current_to_act_seat"] is not None
    assert hand["move_deadline_at"] is not None
    # Roughly 30s out from now.
    deadline = datetime.fromisoformat(hand["move_deadline_at"])
    delta = (deadline - datetime.now(timezone.utc)).total_seconds()
    assert 20 <= delta <= 31


@pytest.mark.asyncio
async def test_deadline_refreshes_for_next_actor_after_action(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    first_actor = _actor_uid(st)
    first_deadline = st["current_hand"]["move_deadline_at"]

    # First actor calls; action passes to the other player, whose deadline is fresh.
    r = await _act(ac, as_user, first_actor, table_id, "call")
    assert r.status_code == 200, r.text

    st2 = await _state(ac, as_user, TEST_USER_ID, table_id)
    assert _actor_uid(st2) != first_actor
    assert st2["current_hand"]["move_deadline_at"] is not None
    assert st2["current_hand"]["move_deadline_at"] != first_deadline


@pytest.mark.asyncio
async def test_expired_deadline_auto_folds_when_facing_a_bet(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    # First to act preflop posts the small blind and faces the big blind.
    assert _actor_to_call(st) > 0
    timed_out = _actor_uid(st)

    await _expire_deadline(db, table_id)

    # Another player merely polling resolves the abandoned turn.
    other = OTHER_USER_ID if timed_out == TEST_USER_ID else TEST_USER_ID
    st2 = await _state(ac, as_user, other, table_id)

    folded_seat = next(
        s for s in st2["current_hand"]["seats"] if uuid.UUID(s["user_id"]) == timed_out
    )
    assert folded_seat["is_folded"] is True


@pytest.mark.asyncio
async def test_completed_hand_has_null_deadline(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    timed_out = _actor_uid(st)
    await _expire_deadline(db, table_id)

    other = OTHER_USER_ID if timed_out == TEST_USER_ID else TEST_USER_ID
    st2 = await _state(ac, as_user, other, table_id)

    # Heads-up: the auto-fold ends the hand uncontested → nobody on the clock.
    hand = st2["current_hand"]
    assert hand["status"] == "complete"
    assert hand["current_to_act_seat"] is None
    assert hand["move_deadline_at"] is None


@pytest.mark.asyncio
async def test_expired_deadline_auto_checks_when_no_bet(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    # First actor calls → action passes to the big blind, who faces no bet.
    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    first_actor = _actor_uid(st)
    r = await _act(ac, as_user, first_actor, table_id, "call")
    assert r.status_code == 200, r.text

    st2 = await _state(ac, as_user, TEST_USER_ID, table_id)
    assert st2["current_hand"]["street"] == "preflop"
    assert _actor_to_call(st2) == 0  # big blind has the option to check
    bb = _actor_uid(st2)

    await _expire_deadline(db, table_id)

    # The other player polls → the big blind is auto-checked, NOT folded, and
    # the street advances to the flop.
    st3 = await _state(ac, as_user, first_actor, table_id)
    bb_seat = next(s for s in st3["current_hand"]["seats"] if uuid.UUID(s["user_id"]) == bb)
    assert bb_seat["is_folded"] is False
    assert st3["current_hand"]["street"] == "flop"


@pytest.mark.asyncio
async def test_acting_after_expiry_is_rejected_as_not_your_turn(multi, db):
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    assert _actor_to_call(st) > 0  # first actor faces the blind → expiry folds them
    timed_out = _actor_uid(st)
    await _expire_deadline(db, table_id)

    # The timed-out player tries to act late; enforcement folds them first, so
    # their own action no longer applies.
    r = await _act(ac, as_user, timed_out, table_id, "call")
    assert r.status_code == 400, r.text


async def _fold_action_count(db, table_id: str, user_id: uuid.UUID) -> int:
    from sqlalchemy import func  # noqa: PLC0415

    from backend.models import HoldemAction, HoldemHand  # noqa: PLC0415

    hand_ids = (await db.execute(
        select(HoldemHand.id).where(HoldemHand.table_id == uuid.UUID(table_id))
    )).scalars().all()
    if not hand_ids:
        return 0
    return int((await db.execute(
        select(func.count(HoldemAction.id)).where(
            HoldemAction.hand_id.in_(hand_ids),
            HoldemAction.user_id == user_id,
            HoldemAction.action == "fold",
        )
    )).scalar_one())


@pytest.mark.asyncio
async def test_spectator_poll_does_not_enforce_timeout(multi, db):
    """A non-seated viewer polling /state must NOT drive another table's game —
    enforcement (a state mutation) is gated on the caller being seated."""
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await seed_user(db, THIRD_USER_ID, "carol")  # a spectator, never seated
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    timed_out = _actor_uid(st)
    await _expire_deadline(db, table_id)

    # The spectator's poll must leave the timed-out player untouched.
    st_spec = await _state(ac, as_user, THIRD_USER_ID, table_id)
    spec_seat = next(s for s in st_spec["current_hand"]["seats"] if uuid.UUID(s["user_id"]) == timed_out)
    assert spec_seat["is_folded"] is False

    # A SEATED player's poll resolves it.
    other = OTHER_USER_ID if timed_out == TEST_USER_ID else TEST_USER_ID
    st_seated = await _state(ac, as_user, other, table_id)
    seated_seat = next(s for s in st_seated["current_hand"]["seats"] if uuid.UUID(s["user_id"]) == timed_out)
    assert seated_seat["is_folded"] is True


@pytest.mark.asyncio
async def test_deal_response_carries_move_deadline(multi, db):
    """The /deal response body itself must include the fresh deadline so the
    client can render the countdown immediately (not only on the next poll)."""
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    deal_body = await _deal(ac, as_user, TEST_USER_ID, table_id)
    assert deal_body["current_hand"]["move_deadline_at"] is not None


@pytest.mark.asyncio
async def test_timeout_logs_exactly_one_fold_action(multi, db):
    """The forced fold is written to the action log once (for replay/audit), and
    repeated polls do not double-resolve it."""
    ac, as_user = multi
    table_id = await _two_player_table(ac, as_user, db)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    assert _actor_to_call(st) > 0  # first actor faces the blind → fold on timeout
    timed_out = _actor_uid(st)
    assert await _fold_action_count(db, table_id, timed_out) == 0
    await _expire_deadline(db, table_id)

    other = OTHER_USER_ID if timed_out == TEST_USER_ID else TEST_USER_ID
    await _state(ac, as_user, other, table_id)
    await _state(ac, as_user, other, table_id)  # poll again — must not re-fire

    assert await _fold_action_count(db, table_id, timed_out) == 1
