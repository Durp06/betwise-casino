"""
test_pai_gow_routers.py — HTTP integration tests for the PG router triple.

Covers the routes registered by `pai_gow_tables.py`, `pai_gow_game.py`,
`pai_gow_advice.py` end-to-end via the FastAPI test client. Auth uses the
`BETWISE_DEV_USER_ID` bypass (set by conftest).

Streaming-content correctness lives in state.py / optimal_set.py tests;
here we just verify the SSE plumbing returns the right status, headers,
and the final summary JSON event.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models import (
    PaiGowPlayerHand,
    PaiGowRound,
    PaiGowSeat,
    PaiGowStrategyStreak,
    PaiGowTable,
)
from backend.tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_pai_gow_player_hand,
    seed_pai_gow_round,
    seed_pai_gow_seat,
    seed_pai_gow_table,
    seed_user,
)


# ─── Table CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_table_201(client, db):
    await seed_user(db, TEST_USER_ID, "alice")
    resp = await client.post(
        "/api/pai-gow/tables",
        json={"name": "Felt One"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Felt One"
    assert body["min_bet_cents"] == 500   # default
    assert body["max_seats"] == 3


@pytest.mark.asyncio
async def test_create_table_rejects_max_below_min_400(client, db):
    await seed_user(db, TEST_USER_ID, "alice")
    resp = await client.post(
        "/api/pai-gow/tables",
        json={"name": "Bad", "min_bet_cents": 1000, "max_bet_cents": 500},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_tables_returns_seat_counts(client, db):
    await seed_user(db, TEST_USER_ID, "alice")
    await client.post("/api/pai-gow/tables", json={"name": "A"})
    resp = await client.get("/api/pai-gow/tables")
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["name"] == "A" for r in rows)
    assert rows[0]["seats_taken"] == 0
    assert rows[0]["active_round_status"] is None


@pytest.mark.asyncio
async def test_join_table_claims_lowest_open_seat(client, db):
    await seed_user(db, TEST_USER_ID, "alice")
    table = (await client.post("/api/pai-gow/tables", json={"name": "T"})).json()
    resp = await client.post(f"/api/pai-gow/tables/{table['id']}/join")
    assert resp.status_code == 200
    seat = resp.json()
    assert seat["seat_number"] == 1


@pytest.mark.asyncio
async def test_join_idempotent_returns_existing_seat(client, db):
    await seed_user(db, TEST_USER_ID, "alice")
    table = (await client.post("/api/pai-gow/tables", json={"name": "T"})).json()
    a = (await client.post(f"/api/pai-gow/tables/{table['id']}/join")).json()
    b = (await client.post(f"/api/pai-gow/tables/{table['id']}/join")).json()
    assert a["id"] == b["id"]


@pytest.mark.asyncio
async def test_join_two_users_get_distinct_seats(db):
    """Two users joining sequentially get distinct seats (1, 2). Verifies the
    basic correctness of seat assignment.

    The race-retry path itself (savepoint + IntegrityError recompute) cannot
    be triggered under aiosqlite + StaticPool because the shared connection
    serializes transactions; both sessions either see committed data or none.
    On real Postgres, the savepoint pattern is what prevents the 500 — that
    behavior is verified by code review against state._find_or_create_active_round's
    fix B (identical pattern, same exception type, same retry shape).
    """
    await seed_user(db, TEST_USER_ID, "alice")
    await seed_user(db, OTHER_USER_ID, "bob")
    table = await seed_pai_gow_table(db)

    from backend.routers.pai_gow_tables import _join_seat  # noqa: PLC0415
    a = await _join_seat(table.id, TEST_USER_ID, db)
    b = await _join_seat(table.id, OTHER_USER_ID, db)
    assert a.seat_number != b.seat_number
    assert {a.seat_number, b.seat_number} == {1, 2}


@pytest.mark.asyncio
async def test_join_picks_next_open_seat_when_lower_seats_taken(db):
    """If seat 1 is already occupied, _join_seat assigns seat 2. Exercises
    the recompute-occupied + pick-next path that the savepoint retry also
    relies on after an IntegrityError.
    """
    await seed_user(db, TEST_USER_ID, "alice")
    await seed_user(db, OTHER_USER_ID, "bob")
    table = await seed_pai_gow_table(db)
    # Pre-claim seat 1 for alice.
    await seed_pai_gow_seat(db, table.id, TEST_USER_ID, seat_number=1)

    from backend.routers.pai_gow_tables import _join_seat  # noqa: PLC0415
    bob_seat = await _join_seat(table.id, OTHER_USER_ID, db)
    assert bob_seat.seat_number == 2


@pytest.mark.asyncio
async def test_join_returns_409_when_table_is_full(db):
    """When all max_seats are taken, _join_seat returns HTTP 409."""
    from fastapi import HTTPException  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table = await seed_pai_gow_table(db)
    # Fill every seat with placeholder users.
    for i in range(table.max_seats):
        from backend.models import User  # noqa: PLC0415
        import uuid as _u  # noqa: PLC0415
        placeholder_id = _u.uuid4()
        db.add(User(
            id=placeholder_id,
            username=f"placeholder_{i}",
            chip_balance=1_000,
        ))
        await db.flush()
        await seed_pai_gow_seat(db, table.id, placeholder_id, seat_number=i + 1)

    from backend.routers.pai_gow_tables import _join_seat  # noqa: PLC0415
    with pytest.raises(HTTPException) as exc:
        await _join_seat(table.id, TEST_USER_ID, db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_get_state_404_for_unknown_table(client, db):
    await seed_user(db, TEST_USER_ID, "alice")
    resp = await client.get("/api/pai-gow/tables/00000000-0000-0000-0000-000000000099/state")
    assert resp.status_code == 404


# ─── Deal / Set end-to-end ──────────────────────────────────────────────────


async def _create_table_and_sit(client) -> str:
    table = (await client.post("/api/pai-gow/tables", json={"name": "T"})).json()
    await client.post(f"/api/pai-gow/tables/{table['id']}/join")
    return table["id"]


@pytest.mark.asyncio
async def test_deal_endpoint_returns_dealt_hand(client, db):
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table_id = await _create_table_and_sit(client)

    resp = await client.post(
        f"/api/pai-gow/tables/{table_id}/deal",
        json={"bet_cents": 1_000, "fortune_bet_cents": 0},
    )
    assert resp.status_code == 200
    hand = resp.json()
    assert len(hand["dealt_cards"]) == 7
    assert hand["bet_cents"] == 1_000
    assert hand["action_status"] == "dealt"


@pytest.mark.asyncio
async def test_set_endpoint_resolves_hand_for_solo_player(client, db):
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table_id = await _create_table_and_sit(client)

    deal_resp = (await client.post(
        f"/api/pai-gow/tables/{table_id}/deal",
        json={"bet_cents": 1_000, "fortune_bet_cents": 0},
    )).json()
    hand_id = deal_resp["id"]
    dealt = deal_resp["dealt_cards"]

    # Use house way to construct a legal split.
    from backend.game.pai_gow.house_way import foxwoods
    front, back = foxwoods(dealt)

    set_resp = await client.post(
        f"/api/pai-gow/hands/{hand_id}/set",
        json={"front": front, "back": back},
    )
    assert set_resp.status_code == 200
    result = set_resp.json()
    assert result["action_status"] == "resolved"
    assert result["hand_result"] in ("win", "push", "lose")


@pytest.mark.asyncio
async def test_set_endpoint_rejects_foul_400(client, db):
    """If random dealt hand permits a foul-able split, verify 400."""
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table_id = await _create_table_and_sit(client)
    deal_resp = (await client.post(
        f"/api/pai-gow/tables/{table_id}/deal",
        json={"bet_cents": 1_000, "fortune_bet_cents": 0},
    )).json()

    from backend.game.pai_gow.cards import card_sort_key
    from backend.game.pai_gow.evaluator import score_hand
    sorted_cards = sorted(deal_resp["dealt_cards"], key=card_sort_key)
    front = sorted_cards[:2]
    back = sorted_cards[2:]
    if score_hand(front) <= score_hand(back):
        pytest.skip("Random hand doesn't produce a clean foul split")

    resp = await client.post(
        f"/api/pai-gow/hands/{deal_resp['id']}/set",
        json={"front": front, "back": back},
    )
    assert resp.status_code == 400
    assert "foul" in resp.json()["detail"].lower()


# ─── State endpoint card masking (§13) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_state_endpoint_masks_other_players_cards_during_play(other_client, db):
    """During 'playing', other players' dealt_cards are hidden from non-owners.

    Uses `other_client` alone (the conftest fixtures collide on the global
    `app.dependency_overrides` if `client` and `other_client` are both
    requested). Seeds TEST_USER_ID's seat + hand directly so we can verify
    that the OTHER_USER_ID viewer sees them masked.
    """
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "bob", chip_balance=100_000)
    table = await seed_pai_gow_table(db)

    # Alice is seated at seat 1 with a dealt hand on an active round.
    await seed_pai_gow_seat(db, table.id, TEST_USER_ID, seat_number=1)
    rnd = await seed_pai_gow_round(
        db, table.id, status="playing",
        dealer_dealt_cards=[{"suit": "hearts", "value": str(v)} for v in range(2, 9)],
    )
    rnd.playing_started_at = datetime.now(timezone.utc)
    alice_hand = await seed_pai_gow_player_hand(
        db, rnd.id, TEST_USER_ID, action_status="dealt"
    )

    # Bob (other_client) joins and views state.
    await other_client.post(f"/api/pai-gow/tables/{table.id}/join")
    state_resp = await other_client.get(f"/api/pai-gow/tables/{table.id}/state")
    assert state_resp.status_code == 200
    state = state_resp.json()

    alice_in_state = next(
        (h for h in state["hands"] if h["user_id"] == str(TEST_USER_ID)),
        None,
    )
    assert alice_in_state is not None
    assert alice_in_state["dealt_cards"] is None  # masked for Bob
    assert state["round"]["dealer_dealt_cards"] is None  # masked during 'playing'


@pytest.mark.asyncio
async def test_state_shows_finished_round_until_next_deal(client, db):
    """After resolve, `/state` must keep returning the finished round (with
    dealer reveal + hand_result populated) until a new round is dealt.

    Without this contract the polling response goes round=null the instant
    the round resolves, so the frontend never gets to render the win/loss +
    payout result UI — the player sees only the next betting prompt. The
    fix is in `_select_most_recent_round`; this test locks in the shape so
    a future "active-only" reflex can't reintroduce the regression.
    """
    from backend.game.pai_gow.house_way import foxwoods  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table_id = await _create_table_and_sit(client)

    deal_resp = (await client.post(
        f"/api/pai-gow/tables/{table_id}/deal",
        json={"bet_cents": 1_000, "fortune_bet_cents": 0},
    )).json()
    hand_id = deal_resp["id"]
    front, back = foxwoods(deal_resp["dealt_cards"])

    set_resp = (await client.post(
        f"/api/pai-gow/hands/{hand_id}/set",
        json={"front": front, "back": back},
    )).json()
    assert set_resp["hand_result"] in ("win", "push", "lose")

    # After resolve — `/state` must still return the finished round.
    state = (await client.get(f"/api/pai-gow/tables/{table_id}/state")).json()
    assert state["round"] is not None, (
        "Polling `/state` after resolve returned round=null — the frontend "
        "result UI gates on `tableState.round` and `myHand.hand_result`, both "
        "of which depend on this round being present in the response."
    )
    assert state["round"]["status"] == "finished"
    assert state["round"]["dealer_dealt_cards"] is not None  # revealed at 'finished'

    alice_hand = next(
        (h for h in state["hands"] if h["user_id"] == str(TEST_USER_ID)),
        None,
    )
    assert alice_hand is not None
    assert alice_hand["hand_result"] in ("win", "push", "lose")
    assert alice_hand["front_cards"] is not None
    assert alice_hand["back_cards"] is not None

    # Now deal again — the new round (higher round_number) supersedes via
    # `ORDER BY round_number DESC LIMIT 1`, and the prior result vanishes.
    deal2_resp = (await client.post(
        f"/api/pai-gow/tables/{table_id}/deal",
        json={"bet_cents": 1_000, "fortune_bet_cents": 0},
    )).json()
    state2 = (await client.get(f"/api/pai-gow/tables/{table_id}/state")).json()
    assert state2["round"] is not None
    assert state2["round"]["status"] in ("betting", "playing"), (
        "After dealing round N+1, `/state` must return that fresh round, "
        f"not the prior finished round. Got status={state2['round']['status']}."
    )
    alice_hand2 = next(
        (h for h in state2["hands"] if h["user_id"] == str(TEST_USER_ID)),
        None,
    )
    assert alice_hand2 is not None
    assert alice_hand2["id"] == deal2_resp["id"]
    assert alice_hand2["id"] != hand_id
    assert alice_hand2["hand_result"] is None  # fresh hand, not yet resolved


@pytest.mark.asyncio
async def test_state_finished_round_to_late_joiner_has_no_my_hand(other_client, db):
    """A user who joins after a round finishes sees the dealer reveal as
    table context, but has no hand in that round — so on the client
    `state.hands.find(user)` is null, `myHand` is null, and `showResult`
    does not fire (no false "you won/lost" banner for the late joiner).

    Uses `other_client` alone per the fixture-collision constraint
    documented on `test_state_endpoint_masks_other_players_cards_during_play`
    — Alice's seat, hand, and the finished round are seeded directly.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "bob", chip_balance=100_000)
    table = await seed_pai_gow_table(db)

    await seed_pai_gow_seat(db, table.id, TEST_USER_ID, seat_number=1)
    rnd = await seed_pai_gow_round(
        db, table.id, status="finished",
        dealer_dealt_cards=[
            {"suit": "spades", "value": str(v)} for v in (2, 3, 4, 5, 6, 7, 8)
        ],
    )
    rnd.dealer_front = [
        {"suit": "spades", "value": "2"},
        {"suit": "spades", "value": "3"},
    ]
    rnd.dealer_back = [
        {"suit": "spades", "value": "4"},
        {"suit": "spades", "value": "5"},
        {"suit": "spades", "value": "6"},
        {"suit": "spades", "value": "7"},
        {"suit": "spades", "value": "8"},
    ]
    rnd.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    alice_hand = await seed_pai_gow_player_hand(
        db, rnd.id, TEST_USER_ID, action_status="resolved",
    )
    alice_hand.hand_result = "win"
    alice_hand.ante_payout_cents = 1_000
    alice_hand.front_cards = [
        {"suit": "hearts", "value": "A"},
        {"suit": "hearts", "value": "K"},
    ]
    alice_hand.back_cards = [
        {"suit": "hearts", "value": "Q"},
        {"suit": "hearts", "value": "J"},
        {"suit": "hearts", "value": "10"},
        {"suit": "diamonds", "value": "A"},
        {"suit": "diamonds", "value": "K"},
    ]
    alice_hand.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    # Bob joins the table now (post-resolve) and polls.
    await other_client.post(f"/api/pai-gow/tables/{table.id}/join")
    state_resp = await other_client.get(f"/api/pai-gow/tables/{table.id}/state")
    assert state_resp.status_code == 200
    state = state_resp.json()

    # Round + dealer reveal are present — Bob sees the table context.
    assert state["round"] is not None
    assert state["round"]["status"] == "finished"
    assert state["round"]["dealer_dealt_cards"] is not None  # revealed at 'finished'

    # Bob has no hand on this finished round → frontend's `myHand` will be
    # null → showResult is false → no result UI for the late joiner.
    bob_hand = next(
        (h for h in state["hands"] if h["user_id"] == str(OTHER_USER_ID)),
        None,
    )
    assert bob_hand is None


# ─── Advice endpoints (SSE) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pre_advice_returns_sse_with_optimal_split(client, db, mock_anthropic):
    """Pre-advice: streams Chipy text and ends with the optimal split JSON."""
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    table_id = await _create_table_and_sit(client)
    hand = (await client.post(
        f"/api/pai-gow/tables/{table_id}/deal",
        json={"bet_cents": 1_000, "fortune_bet_cents": 0},
    )).json()

    resp = await client.post(f"/api/pai-gow/advice/{hand['id']}/pre")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    # Final JSON event should contain the optimal split.
    body = resp.text
    assert "optimal_front" in body
    assert "optimal_back" in body
    assert '"phase": "pre"' in body


@pytest.mark.asyncio
async def test_pre_advice_rejects_non_owner_with_403(client, db, mock_anthropic):
    """Owner-only: requester can't see advice for someone else's hand.

    Seeds OTHER_USER_ID's hand directly; `client` (TEST_USER_ID) requests it
    and must 403.
    """
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "bob", chip_balance=100_000)
    table = await seed_pai_gow_table(db)
    await seed_pai_gow_seat(db, table.id, OTHER_USER_ID, seat_number=1)
    rnd = await seed_pai_gow_round(db, table.id, status="playing")
    bob_hand = await seed_pai_gow_player_hand(db, rnd.id, OTHER_USER_ID)

    resp = await client.post(f"/api/pai-gow/advice/{bob_hand.id}/pre")
    assert resp.status_code == 403


# ─── Fortune pool endpoint ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fortune_pool_endpoint_returns_seeded_amount(client, db):
    """Fortune pool is seeded by the engine fixture at $1000 (100,000c)."""
    await seed_user(db, TEST_USER_ID, "alice")
    resp = await client.get("/api/pai-gow/fortune-pool")
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount_cents"] == 100_000
    assert body["seed_cents"] == 100_000
