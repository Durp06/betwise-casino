"""
test_poker_endpoints.py — integration tests for poker_tables.py.

Covers AC-R1, R2, R3, R4 (partially), R9.
"""
from __future__ import annotations

import pytest

from backend.tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_user,
)


@pytest.mark.asyncio
async def test_create_tournament_succeeds_and_deducts_bankroll(client, db):
    """AC-R1, AC-R3."""
    await seed_user(db, TEST_USER_ID, "pokerstud", chip_balance=100_000)
    resp = await client.post(
        "/api/poker/tournaments",
        json={
            "bot_count": 3,
            "advice_mode": "odds",
            "buy_in_cents": 10_000,
            "starting_stack_chips": 1500,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["bot_count"] == 3
    assert data["advice_mode"] == "odds"
    assert data["buy_in_cents"] == 10_000
    assert data["status"] == "active"

    # Bankroll should be deducted
    me_resp = await client.get("/api/users/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["chip_balance"] == 90_000


@pytest.mark.asyncio
async def test_create_tournament_insufficient_bankroll_returns_400(client, db):
    """AC-R2."""
    await seed_user(db, TEST_USER_ID, "broke", chip_balance=1_000)
    resp = await client.post(
        "/api/poker/tournaments",
        json={
            "bot_count": 3,
            "advice_mode": "odds",
            "buy_in_cents": 10_000,
            "starting_stack_chips": 1500,
        },
    )
    assert resp.status_code == 400
    assert "insufficient" in resp.json()["detail"].lower() or "bankroll" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_tournament_validates_bot_count(client, db):
    await seed_user(db, TEST_USER_ID, "validator", chip_balance=100_000)
    # 1 bot is too few
    resp = await client.post(
        "/api/poker/tournaments",
        json={
            "bot_count": 1,
            "advice_mode": "odds",
            "buy_in_cents": 10_000,
            "starting_stack_chips": 1500,
        },
    )
    assert resp.status_code == 400
    # 8 bots is too many
    resp = await client.post(
        "/api/poker/tournaments",
        json={
            "bot_count": 8,
            "advice_mode": "odds",
            "buy_in_cents": 10_000,
            "starting_stack_chips": 1500,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_state_returns_seats_with_archetypes(client, db):
    await seed_user(db, TEST_USER_ID, "stater", chip_balance=100_000)
    resp = await client.post(
        "/api/poker/tournaments",
        json={
            "bot_count": 4,
            "advice_mode": "reads",
            "buy_in_cents": 5_000,
            "starting_stack_chips": 1500,
        },
    )
    assert resp.status_code == 201
    tid = resp.json()["id"]

    state = await client.get(f"/api/poker/tournaments/{tid}/state")
    assert state.status_code == 200
    body = state.json()
    assert len(body["seats"]) == 5  # 1 human + 4 bots
    assert body["your_seat_number"] == 0
    # Bots have archetype names
    bot_archetypes = [s["archetype_name"] for s in body["seats"] if s["is_bot"]]
    assert all(a is not None for a in bot_archetypes)
    assert len(bot_archetypes) == 4
    # Human has no archetype
    human = next(s for s in body["seats"] if not s["is_bot"])
    assert human["archetype_name"] is None
    assert human["user_id"] is not None


@pytest.mark.asyncio
async def test_state_refuses_non_participant(client, db):
    """AC-R9 (authorization). Create a tournament for OTHER_USER directly
    in the DB, then try to read it as TEST_USER — should 403."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.models import PokerSeat, PokerTournament  # noqa: PLC0415

    # Seed OTHER_USER (the "owner")
    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    await seed_user(db, TEST_USER_ID, "intruder", chip_balance=100_000)

    # Create a tournament owned by OTHER_USER directly
    t = PokerTournament(
        id=_uuid.uuid4(),
        bot_count=2,
        advice_mode="odds",
        buy_in_cents=1_000,
        starting_stack_chips=1500,
        hands_per_level=10,
        seed=42,
        status="active",
        button_seat=0,
        current_hand_number=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(t)
    await db.flush()
    db.add(PokerSeat(
        id=_uuid.uuid4(),
        tournament_id=t.id,
        user_id=OTHER_USER_ID,
        seat_number=0,
        archetype_name=None,
        starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=False,
        joined_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    # TEST_USER tries to read it
    bad = await client.get(f"/api/poker/tournaments/{t.id}/state")
    assert bad.status_code == 403


@pytest.mark.asyncio
async def test_list_my_tournaments_returns_only_mine(client, db):
    """List endpoint filters by current_user — confirms via direct DB-seeded
    tournament owned by someone else not appearing in the list."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.models import PokerSeat, PokerTournament  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "mine", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "other", chip_balance=100_000)

    # I create one via the API
    r1 = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    my_tid = r1.json()["id"]

    # Seed a tournament for OTHER_USER directly
    other_t = PokerTournament(
        id=_uuid.uuid4(),
        bot_count=3, advice_mode="reads", buy_in_cents=1_000,
        starting_stack_chips=1500, hands_per_level=10,
        seed=99, status="active", button_seat=0, current_hand_number=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(other_t)
    await db.flush()
    db.add(PokerSeat(
        id=_uuid.uuid4(), tournament_id=other_t.id, user_id=OTHER_USER_ID,
        seat_number=0, archetype_name=None,
        starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=False,
        joined_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    mine = await client.get("/api/poker/tournaments")
    assert mine.status_code == 200
    ids = [t["id"] for t in mine.json()]
    assert my_tid in ids
    assert str(other_t.id) not in ids  # I should not see the other user's


@pytest.mark.asyncio
async def test_state_404_for_nonexistent_tournament(client, db):
    await seed_user(db, TEST_USER_ID, "wanderer", chip_balance=100_000)
    resp = await client.get("/api/poker/tournaments/00000000-0000-0000-0000-000000000000/state")
    assert resp.status_code == 404
