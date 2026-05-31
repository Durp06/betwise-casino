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


# ─── Deal + act integration (AC-R6, AC-R5) ────────────────────────────────────


@pytest.mark.asyncio
async def test_deal_creates_first_hand_and_returns_state(client, db):
    """AC-R5 (state reconstruction) — deal produces a fresh hand with board=[]
    preflop and the human's hole cards visible to the human."""
    await seed_user(db, TEST_USER_ID, "dealer", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]

    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    assert deal.status_code == 200
    body = deal.json()
    hand = body["current_hand"]
    assert hand is not None
    assert hand["hand_number"] == 1
    assert hand["street"] in ("preflop", "flop", "turn", "river", "complete")
    # Human is seat 0 — should have 2 hole cards visible
    seats = hand["seats"]
    me = next(s for s in seats if s["seat_number"] == 0)
    assert len(me["hole_cards"]) == 2
    for card in me["hole_cards"]:
        assert card is not None
        assert "suit" in card and "value" in card


@pytest.mark.asyncio
async def test_deal_is_idempotent_returns_active_hand(client, db):
    await seed_user(db, TEST_USER_ID, "idempotent", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]

    d1 = await client.post(f"/api/poker/tournaments/{tid}/deal")
    d2 = await client.post(f"/api/poker/tournaments/{tid}/deal")
    assert d1.status_code == 200
    assert d2.status_code == 200
    # Same hand id — second call is idempotent
    assert d1.json()["current_hand"]["id"] == d2.json()["current_hand"]["id"]


@pytest.mark.asyncio
async def test_state_masks_opponent_hole_cards(client, db):
    """AC-R4 — opponent hole cards are [null, null] during play."""
    await seed_user(db, TEST_USER_ID, "masker", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 3, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]
    await client.post(f"/api/poker/tournaments/{tid}/deal")

    state = await client.get(f"/api/poker/tournaments/{tid}/state")
    assert state.status_code == 200
    hand = state.json()["current_hand"]
    if hand is None:
        return
    seats = hand["seats"]
    me = next(s for s in seats if s["seat_number"] == 0)
    others = [s for s in seats if s["seat_number"] != 0]
    # Human sees their own cards
    for c in me["hole_cards"]:
        assert c is not None
    # Opponent cards masked
    for opp in others:
        for c in opp["hole_cards"]:
            assert c is None


@pytest.mark.asyncio
async def test_act_advances_state_and_drives_bots(client, db):
    """AC-R6 — submitting a human action resolves bots up to next human turn
    or hand end. Verifies the action log grows and the hand progresses."""
    await seed_user(db, TEST_USER_ID, "actor", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    hand0 = deal.json()["current_hand"]
    actions_before = len(hand0["actions"])

    # Whose turn is it?
    next_seat = hand0["current_to_act_seat"]
    if next_seat == 0:
        # Human's turn — fold
        a = await client.post(f"/api/poker/tournaments/{tid}/act", json={"action": "fold", "amount": 0})
        assert a.status_code == 200
        hand_after = a.json()["current_hand"]
        # If hand wasn't completed by this fold (multi-bot still in), expect more actions
        assert hand_after is not None
        assert len(hand_after["actions"]) > actions_before


@pytest.mark.asyncio
async def test_act_requires_active_hand(client, db):
    await seed_user(db, TEST_USER_ID, "premature", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]
    # No deal — act should fail
    a = await client.post(f"/api/poker/tournaments/{tid}/act", json={"action": "fold", "amount": 0})
    assert a.status_code == 400


@pytest.mark.asyncio
async def test_replay_endpoint_for_finished_hand(client, db):
    """AC-R10 — once a hand finishes, replay returns the full action log +
    revealed hole cards."""
    await seed_user(db, TEST_USER_ID, "replayer", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    hand_id = deal.json()["current_hand"]["id"]

    # Fold immediately to end the hand
    next_seat = deal.json()["current_hand"]["current_to_act_seat"]
    if next_seat == 0:
        await client.post(f"/api/poker/tournaments/{tid}/act", json={"action": "fold", "amount": 0})

    replay = await client.get(f"/api/poker/hands/{hand_id}/replay")
    assert replay.status_code == 200
    body = replay.json()
    assert body["hand_number"] == 1
    assert isinstance(body["actions"], list)
    assert isinstance(body["seats"], list)


# ─── Chipy SSE advice (AC-R7, R8, R9) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_advice_sse_streams_chunks_and_final_json(client, db, mocker):
    """AC-R7 — SSE stream returns text chunks followed by a final JSON event
    with the PokerAdviceOut shape."""
    await seed_user(db, TEST_USER_ID, "advisee", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    hand_id = deal.json()["current_hand"]["id"]

    # Patch the Anthropic shim to yield fixed chunks
    async def _fake_stream(system, user):
        yield "Pot odds say "
        yield "fold is fine here."

    mocker.patch("backend.routers.poker_advice._stream_anthropic_poker", _fake_stream)

    resp = await client.post(f"/api/poker/hands/{hand_id}/advice")
    assert resp.status_code == 200
    body = resp.text
    assert "Pot odds say" in body or "fold is fine" in body
    # Final SSE event must be valid JSON with PokerAdviceOut keys
    assert '"confidence_tier"' in body
    assert '"verdict"' in body


@pytest.mark.asyncio
async def test_advice_refuses_non_participant(client, db, mocker):
    """AC-R9 — only the seat's owner can request advice."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.models import (  # noqa: PLC0415
        PokerHand,
        PokerHandSeat,
        PokerSeat,
        PokerTournament,
    )

    # Seed OTHER_USER as the tournament owner
    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    await seed_user(db, TEST_USER_ID, "intruder", chip_balance=100_000)

    t = PokerTournament(
        id=_uuid.uuid4(),
        bot_count=2, advice_mode="odds", buy_in_cents=1_000,
        starting_stack_chips=1500, hands_per_level=10,
        seed=42, status="active", button_seat=0, current_hand_number=1,
        created_at=datetime.now(timezone.utc),
    )
    db.add(t)
    await db.flush()
    db.add(PokerSeat(
        id=_uuid.uuid4(), tournament_id=t.id, user_id=OTHER_USER_ID,
        seat_number=0, archetype_name=None,
        starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=False,
        joined_at=datetime.now(timezone.utc),
    ))
    hand = PokerHand(
        id=_uuid.uuid4(),
        tournament_id=t.id, hand_number=1, button_seat=0,
        seed=42, small_blind=10, big_blind=20, ante=0,
        board=[], pot_total=30, side_pots=[],
        street="preflop", current_bet_to_match=20,
        current_to_act_seat=0, last_aggressor_seat=None,
        min_raise_increment=20, status="active", result=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    await db.flush()
    db.add(PokerHandSeat(
        id=_uuid.uuid4(), hand_id=hand.id, seat_number=0,
        hole_cards=[{"suit": "spades", "value": "A"}, {"suit": "hearts", "value": "A"}],
        starting_stack=1500, final_stack=1490, contributed=10, current_bet=10,
        is_folded=False, is_all_in=False, has_acted_this_street=False,
    ))
    await db.commit()

    async def _no_stream(system, user):
        if False:
            yield ""

    mocker.patch("backend.routers.poker_advice._stream_anthropic_poker", _no_stream)
    resp = await client.post(f"/api/poker/hands/{hand.id}/advice")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_session_review_lists_human_actions(client, db):
    """AC-R11 — session review aggregates the user's actions across hands."""
    await seed_user(db, TEST_USER_ID, "reviewer", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")

    next_seat = deal.json()["current_hand"]["current_to_act_seat"]
    if next_seat == 0:
        await client.post(f"/api/poker/tournaments/{tid}/act", json={"action": "fold", "amount": 0})

    review = await client.get(f"/api/poker/tournaments/{tid}/review")
    assert review.status_code == 200
    body = review.json()
    assert body["total_actions"] >= 0
    assert "deterministic_actions" in body
    assert "ev_lost_chips" in body
    assert isinstance(body["actions"], list)
