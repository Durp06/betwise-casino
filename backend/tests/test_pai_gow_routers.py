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
