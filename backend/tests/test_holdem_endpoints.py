"""
test_holdem_endpoints.py — multiplayer Texas Hold'em HTTP endpoint tests.

Covers spec §AC-E1..E8. Two (or three) humans share one table via a single
AsyncClient whose `get_current_user` override reads a mutable holder, so the
acting identity can be switched per request (FastAPI dependency_overrides are
global per app, so two fixed-identity clients would collide).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import OTHER_USER_ID, TEST_USER_ID, seed_user

THIRD_USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest_asyncio.fixture
async def multi(db):
    """An AsyncClient + a `as_user(uid)` switch sharing one db session."""
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


async def _create_table(ac, as_user, uid, **kw) -> str:
    as_user(uid)
    body = {"name": "Test Holdem", "small_blind": 50, "big_blind": 100,
            "min_buy_in": 2_000, "max_buy_in": 20_000, "max_seats": 6}
    body.update(kw)
    r = await ac.post("/api/holdem/tables", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _join(ac, as_user, uid, table_id, buy_in=10_000):
    as_user(uid)
    return await ac.post(f"/api/holdem/tables/{table_id}/join", json={"buy_in": buy_in})


async def _state(ac, as_user, uid, table_id) -> dict:
    as_user(uid)
    r = await ac.get(f"/api/holdem/tables/{table_id}/state")
    assert r.status_code == 200, r.text
    return r.json()


async def _deal(ac, as_user, uid, table_id):
    as_user(uid)
    return await ac.post(f"/api/holdem/tables/{table_id}/deal")


async def _act(ac, as_user, uid, table_id, action, amount=0):
    as_user(uid)
    return await ac.post(f"/api/holdem/tables/{table_id}/act", json={"action": action, "amount": amount})


async def _shove_all(ac, as_user, viewer_uid, table_id, max_steps=40) -> dict:
    """Every actor in turn goes all-in until the hand completes."""
    for _ in range(max_steps):
        st = await _state(ac, as_user, viewer_uid, table_id)
        hand = st["current_hand"]
        if hand is None or hand["status"] == "complete":
            return st
        cta = hand["current_to_act_seat"]
        if cta is None:
            return st
        actor = next(s["user_id"] for s in hand["seats"] if s["seat_number"] == cta)
        r = await _act(ac, as_user, actor, table_id, "all_in")
        assert r.status_code == 200, r.text
    raise AssertionError("hand did not complete within step budget")


async def _play_passively(ac, as_user, viewer_uid, table_id, max_steps=80) -> dict:
    """Drive a hand to completion with every actor checking, or calling when
    facing a bet (e.g. the blinds preflop)."""
    for _ in range(max_steps):
        st = await _state(ac, as_user, viewer_uid, table_id)
        hand = st["current_hand"]
        if hand is None or hand["status"] == "complete":
            return st
        cta = hand["current_to_act_seat"]
        if cta is None:
            return st
        seat = next(s for s in hand["seats"] if s["seat_number"] == cta)
        to_call = hand["current_bet_to_match"] - seat["current_bet"]
        action = "call" if to_call > 0 else "check"
        r = await _act(ac, as_user, seat["user_id"], table_id, action)
        assert r.status_code == 200, r.text
    raise AssertionError("hand did not complete within step budget")


async def _seed_two(db):
    await seed_user(db, TEST_USER_ID, "alice", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "bob", chip_balance=100_000)


# ─── AC-E1 create ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_table_and_list(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    as_user(TEST_USER_ID)
    r = await ac.get("/api/holdem/tables")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["id"] == table_id and row["seats_taken"] == 0 for row in rows)


@pytest.mark.asyncio
async def test_create_table_rejects_bad_blinds(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    as_user(TEST_USER_ID)
    r = await ac.post("/api/holdem/tables", json={
        "name": "bad", "small_blind": 100, "big_blind": 50,
        "min_buy_in": 2_000, "max_buy_in": 20_000, "max_seats": 6,
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_create_table_rejects_bad_seat_count(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    as_user(TEST_USER_ID)
    r = await ac.post("/api/holdem/tables", json={
        "name": "huge", "small_blind": 50, "big_blind": 100,
        "min_buy_in": 2_000, "max_buy_in": 20_000, "max_seats": 12,
    })
    assert r.status_code == 400


# ─── AC-E2 join ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_join_deducts_bankroll_and_takes_lowest_seat(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)

    r = await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    assert r.status_code == 200, r.text
    assert r.json()["seat_number"] == 0
    assert r.json()["stack"] == 10_000

    r2 = await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=5_000)
    assert r2.status_code == 200
    assert r2.json()["seat_number"] == 1

    # bankroll deducted
    as_user(TEST_USER_ID)
    me = (await ac.get("/api/users/me")).json()
    assert me["chip_balance"] == 90_000


@pytest.mark.asyncio
async def test_join_idempotent(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    r = await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    assert r.status_code == 200
    assert r.json()["seat_number"] == 0
    # not double-charged
    as_user(TEST_USER_ID)
    assert (await ac.get("/api/users/me")).json()["chip_balance"] == 90_000


@pytest.mark.asyncio
async def test_join_insufficient_bankroll(multi, db):
    ac, as_user = multi
    await seed_user(db, TEST_USER_ID, "poor", chip_balance=1_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    r = await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_join_out_of_range_buy_in(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    r = await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=500)  # below min
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_join_full_returns_409(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    await seed_user(db, THIRD_USER_ID, "carol", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID, max_seats=2)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, OTHER_USER_ID, table_id)
    r = await _join(ac, as_user, THIRD_USER_ID, table_id)
    assert r.status_code == 409


# ─── AC-E3 leave ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_leave_cashes_out_stack(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    as_user(TEST_USER_ID)
    assert (await ac.get("/api/users/me")).json()["chip_balance"] == 90_000
    r = await ac.post(f"/api/holdem/tables/{table_id}/leave")
    assert r.status_code == 200
    assert (await ac.get("/api/users/me")).json()["chip_balance"] == 100_000


# ─── AC-E4 deal ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deal_requires_two_players(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    r = await _deal(ac, as_user, TEST_USER_ID, table_id)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_deal_posts_blinds_and_deals_hole_cards(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)

    r = await _deal(ac, as_user, TEST_USER_ID, table_id)
    assert r.status_code == 200, r.text
    hand = r.json()["current_hand"]
    assert hand is not None
    assert hand["street"] == "preflop"
    # pot displays the posted blinds (SB 50 + BB 100)
    assert hand["pot_total"] == 150
    assert hand["current_bet_to_match"] == 100
    assert hand["current_to_act_seat"] is not None
    # two seats, each with two hole cards
    assert len(hand["seats"]) == 2
    for s in hand["seats"]:
        assert len(s["hole_cards"]) == 2


@pytest.mark.asyncio
async def test_deal_idempotent(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, OTHER_USER_ID, table_id)
    r1 = await _deal(ac, as_user, TEST_USER_ID, table_id)
    r2 = await _deal(ac, as_user, OTHER_USER_ID, table_id)
    assert r1.json()["current_hand"]["id"] == r2.json()["current_hand"]["id"]


# ─── AC-E8 masking ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_opponent_hole_cards_masked_during_play(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, OTHER_USER_ID, table_id)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    st = await _state(ac, as_user, TEST_USER_ID, table_id)
    my_seat = st["your_seat_number"]
    for s in st["current_hand"]["seats"]:
        if s["seat_number"] == my_seat:
            assert all(c is not None for c in s["hole_cards"])  # I see mine
        else:
            assert s["hole_cards"] == [None, None]  # opponent masked


# ─── AC-E5 act / turn guard ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_act_not_your_turn_rejected(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, OTHER_USER_ID, table_id)
    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()
    cta = st["current_hand"]["current_to_act_seat"]
    not_actor = next(s["user_id"] for s in st["current_hand"]["seats"] if s["seat_number"] != cta)
    r = await _act(ac, as_user, not_actor, table_id, "call")
    assert r.status_code == 400
    assert "turn" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_act_without_seat_rejected(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    await seed_user(db, THIRD_USER_ID, "outsider", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id)
    await _join(ac, as_user, OTHER_USER_ID, table_id)
    await _deal(ac, as_user, TEST_USER_ID, table_id)
    r = await _act(ac, as_user, THIRD_USER_ID, table_id, "call")
    assert r.status_code == 403


# ─── AC-E6/E7 full hands ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fold_ends_hand_and_awards_blinds(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()

    cta = st["current_hand"]["current_to_act_seat"]
    actor = next(s["user_id"] for s in st["current_hand"]["seats"] if s["seat_number"] == cta)
    r = await _act(ac, as_user, actor, table_id, "fold")
    assert r.status_code == 200, r.text

    final = await _state(ac, as_user, TEST_USER_ID, table_id)
    assert final["current_hand"]["status"] == "complete"
    # chips conserved across both seats
    assert sum(s["stack"] for s in final["seats"]) == 20_000
    # the folder lost exactly the small blind (50); folder is button/SB preflop in HU
    stacks = sorted(s["stack"] for s in final["seats"])
    assert stacks == [9_950, 10_050]


@pytest.mark.asyncio
async def test_full_heads_up_hand_to_showdown(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    final = await _play_passively(ac, as_user, TEST_USER_ID, table_id)
    hand = final["current_hand"]
    assert hand["status"] == "complete"
    assert hand["street"] == "complete"
    assert len(hand["board"]) == 5  # checked down to the river
    assert hand["result"] is not None
    # chip conservation: nothing created or destroyed (no rake)
    assert sum(s["stack"] for s in final["seats"]) == 20_000


@pytest.mark.asyncio
async def test_button_rotates_between_hands(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)

    await _deal(ac, as_user, TEST_USER_ID, table_id)
    h1 = (await _state(ac, as_user, TEST_USER_ID, table_id))["current_hand"]
    btn1 = next(s["table_seat_number"] for s in h1["seats"] if s["seat_number"] == h1["button_seat"])
    await _play_passively(ac, as_user, TEST_USER_ID, table_id)

    await _deal(ac, as_user, TEST_USER_ID, table_id)
    h2 = (await _state(ac, as_user, TEST_USER_ID, table_id))["current_hand"]
    assert h2["hand_number"] == h1["hand_number"] + 1
    btn2 = next(s["table_seat_number"] for s in h2["seats"] if s["seat_number"] == h2["button_seat"])
    assert btn2 != btn1  # button moved to the other chair


@pytest.mark.asyncio
async def test_three_handed_turn_order_and_showdown(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    await seed_user(db, THIRD_USER_ID, "carol", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, THIRD_USER_ID, table_id, buy_in=10_000)

    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()
    hand = st["current_hand"]
    assert len(hand["seats"]) == 3
    # 3-handed: UTG (=button) acts first preflop after SB/BB are posted.
    # blinds: SB 50 + BB 100 → pot 150
    assert hand["pot_total"] == 150

    final = await _play_passively(ac, as_user, TEST_USER_ID, table_id)
    assert final["current_hand"]["status"] == "complete"
    assert sum(s["stack"] for s in final["seats"]) == 30_000


@pytest.mark.asyncio
async def test_raise_reopens_action_and_advances_streets(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()
    hand = st["current_hand"]
    cta = hand["current_to_act_seat"]
    sb = next(s["user_id"] for s in hand["seats"] if s["seat_number"] == cta)

    # Below-min-raise is rejected (cbtm 100, min increment 100; raise-to 150 → +50).
    r = await _act(ac, as_user, sb, table_id, "raise", 150)
    assert r.status_code == 400

    # A valid raise to 300 updates the bet level and reopens action for the BB.
    r = await _act(ac, as_user, sb, table_id, "raise", 300)
    assert r.status_code == 200, r.text
    h2 = (await _state(ac, as_user, TEST_USER_ID, table_id))["current_hand"]
    assert h2["current_bet_to_match"] == 300
    bb = next(s["user_id"] for s in h2["seats"] if s["seat_number"] == h2["current_to_act_seat"])
    assert bb != sb  # action reopened to the other player

    # BB calls → preflop closes → flop (3 cards). Chips conserved live.
    r = await _act(ac, as_user, bb, table_id, "call")
    assert r.status_code == 200, r.text
    h3 = (await _state(ac, as_user, TEST_USER_ID, table_id))["current_hand"]
    assert h3["street"] == "flop"
    assert len(h3["board"]) == 3
    live_total = sum(s["final_stack"] for s in h3["seats"]) + h3["pot_total"]
    assert live_total == 20_000

    # Postflop HU: BB acts first. A flop bet advances the bet level and is called → turn.
    actor = next(s["user_id"] for s in h3["seats"] if s["seat_number"] == h3["current_to_act_seat"])
    r = await _act(ac, as_user, actor, table_id, "raise", 200)
    assert r.status_code == 200, r.text
    h4 = (await _state(ac, as_user, TEST_USER_ID, table_id))["current_hand"]
    assert h4["current_bet_to_match"] == 200
    caller = next(s["user_id"] for s in h4["seats"] if s["seat_number"] == h4["current_to_act_seat"])
    r = await _act(ac, as_user, caller, table_id, "call")
    assert r.status_code == 200, r.text
    h5 = (await _state(ac, as_user, TEST_USER_ID, table_id))["current_hand"]
    assert h5["street"] == "turn"
    assert len(h5["board"]) == 4


@pytest.mark.asyncio
async def test_side_pot_three_handed_all_in(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    await seed_user(db, THIRD_USER_ID, "carol", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=3_000)   # short stack
    await _join(ac, as_user, THIRD_USER_ID, table_id, buy_in=10_000)
    await _deal(ac, as_user, TEST_USER_ID, table_id)

    final = await _shove_all(ac, as_user, TEST_USER_ID, table_id)
    hand = final["current_hand"]
    assert hand["status"] == "complete"
    assert len(hand["board"]) == 5
    # commitments {3000, 10000, 10000} → a main pot + one side pot.
    assert len(hand["side_pots"]) == 2
    # chip conservation across the table (no rake).
    assert sum(s["stack"] for s in final["seats"]) == 23_000


@pytest.mark.asyncio
async def test_folded_player_stays_mucked_at_showdown(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    await seed_user(db, THIRD_USER_ID, "carol", chip_balance=100_000)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, THIRD_USER_ID, table_id, buy_in=10_000)
    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()

    cta = st["current_hand"]["current_to_act_seat"]
    folder = next(s["user_id"] for s in st["current_hand"]["seats"] if s["seat_number"] == cta)
    assert (await _act(ac, as_user, folder, table_id, "fold")).status_code == 200

    final = await _play_passively(ac, as_user, TEST_USER_ID, table_id)
    fhand = final["current_hand"]
    assert fhand["status"] == "complete"

    # View as a NON-folder; the folded player's cards stay mucked, the other
    # showdown contestant is revealed.
    viewer = next(s["user_id"] for s in fhand["seats"] if not s["is_folded"])
    vhand = (await _state(ac, as_user, viewer, table_id))["current_hand"]
    folded = [s for s in vhand["seats"] if s["is_folded"]]
    assert len(folded) == 1
    assert folded[0]["hole_cards"] == [None, None]
    contender = next(s for s in vhand["seats"] if not s["is_folded"] and s["user_id"] != viewer)
    assert all(c is not None for c in contender["hole_cards"])


@pytest.mark.asyncio
async def test_all_in_leaver_keeps_showdown_equity(multi, db):
    """Regression for the critical bug: leaving while all-in must NOT force-fold
    the player out of a pot they're entitled to contest."""
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()
    hand = st["current_hand"]
    cta = hand["current_to_act_seat"]
    shover = next(s["user_id"] for s in hand["seats"] if s["seat_number"] == cta)
    other = next(s["user_id"] for s in hand["seats"] if s["seat_number"] != cta)

    assert (await _act(ac, as_user, shover, table_id, "all_in")).status_code == 200

    # Shover leaves WHILE all-in.
    as_user(shover)
    assert (await ac.post(f"/api/holdem/tables/{table_id}/leave")).status_code == 200

    # Not force-folded: still contesting, seat retained (sitting out), hand alive.
    st2 = await _state(ac, as_user, other, table_id)
    shover_hs = next(s for s in st2["current_hand"]["seats"] if s["user_id"] == shover)
    assert shover_hs["is_folded"] is False
    assert st2["current_hand"]["status"] == "active"
    assert any(s["user_id"] == shover for s in st2["seats"])

    # Opponent calls → runout → showdown; both contest, chips conserved.
    assert (await _act(ac, as_user, other, table_id, "call")).status_code == 200
    final = await _state(ac, as_user, other, table_id)
    fhand = final["current_hand"]
    assert fhand["status"] == "complete"
    assert len(fhand["board"]) == 5
    assert all(not s["is_folded"] for s in fhand["seats"])  # neither folded → both revealed
    assert sum(s["stack"] for s in final["seats"]) == 20_000


@pytest.mark.asyncio
async def test_all_in_runs_out_board_and_resolves(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()

    # First-to-act shoves all-in; the other calls (auto all-in for equal stacks).
    cta = st["current_hand"]["current_to_act_seat"]
    shover = next(s["user_id"] for s in st["current_hand"]["seats"] if s["seat_number"] == cta)
    r = await _act(ac, as_user, shover, table_id, "all_in")
    assert r.status_code == 200, r.text

    st2 = await _state(ac, as_user, TEST_USER_ID, table_id)
    cta2 = st2["current_hand"]["current_to_act_seat"]
    caller = next(s["user_id"] for s in st2["current_hand"]["seats"] if s["seat_number"] == cta2)
    r = await _act(ac, as_user, caller, table_id, "call")
    assert r.status_code == 200, r.text

    final = await _state(ac, as_user, TEST_USER_ID, table_id)
    hand = final["current_hand"]
    assert hand["status"] == "complete"
    assert len(hand["board"]) == 5  # board ran out automatically
    # equal stacks all-in → no side pot, winner (or chop) holds all the chips
    assert sum(s["stack"] for s in final["seats"]) == 20_000
    # at showdown, both non-folded hands are revealed
    revealed = [s for s in hand["seats"] if not s["is_folded"]]
    assert all(all(c is not None for c in s["hole_cards"]) for s in revealed)


@pytest.mark.asyncio
async def test_leave_during_hand_folds_and_cashes_out(multi, db):
    ac, as_user = multi
    await _seed_two(db)
    table_id = await _create_table(ac, as_user, TEST_USER_ID)
    await _join(ac, as_user, TEST_USER_ID, table_id, buy_in=10_000)
    await _join(ac, as_user, OTHER_USER_ID, table_id, buy_in=10_000)
    st = (await _deal(ac, as_user, TEST_USER_ID, table_id)).json()

    # Whoever is NOT to act leaves mid-hand; they fold out and cash their stack.
    cta = st["current_hand"]["current_to_act_seat"]
    leaver = next(s["user_id"] for s in st["current_hand"]["seats"] if s["seat_number"] != cta)
    stayer = next(s["user_id"] for s in st["current_hand"]["seats"] if s["seat_number"] == cta)
    as_user(leaver)
    r = await ac.post(f"/api/holdem/tables/{table_id}/leave")
    assert r.status_code == 200, r.text

    # The hand ends (sole survivor wins); leaver's seat is gone.
    final = await _state(ac, as_user, stayer, table_id)
    assert len(final["seats"]) == 1
    assert final["current_hand"]["status"] == "complete"

    # Leaver's bankroll: 100k − 10k buy-in + cashed-out remaining stack.
    as_user(leaver)
    leaver_bankroll = (await ac.get("/api/users/me")).json()["chip_balance"]
    # Stayer's at-table stack + leaver's cash-out conserve the 20k bought in.
    table_chips = sum(s["stack"] for s in final["seats"])
    assert table_chips + (leaver_bankroll - 90_000) == 20_000
