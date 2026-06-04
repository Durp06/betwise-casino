"""
test_poker_review.py — backend ACs for Poker Review PR2 (compute-on-read).

Covers specs/poker-review-pr2.md backend acceptance criteria:
- finished hold'em hand → HandReview with a verdict for each caller action and
  NONE for opponents;
- non-participant caller → 403;
- opponent hole cards absent from the response;
- chips→bb conversion uses the table big blind (assert amount_bb for a known bet);
- reproducible (same hand twice → identical verdicts/equities);
- solo per-hand + tournament endpoints (HandReview / GameReview);
- GameReview aggregation of overall_accuracy / total_ev_lost_bb.
"""
from __future__ import annotations

import pytest

from backend.tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_holdem_hand,
    seed_holdem_table,
    seed_user,
)


def _c(value: str, suit: str) -> dict:
    return {"suit": suit, "value": value}


async def _seed_finished_holdem_hand(db, *, big_blind: int = 100, small_blind: int = 50):
    """Heads-up finished hand: hero (seat 0, BTN/SB) faces the BB and folds
    preflop after the BB checks back is not possible — hero acts first HU. The
    action log is a legal post-blind sequence the replay can re-run."""
    table = await seed_holdem_table(db, small_blind=small_blind, big_blind=big_blind)
    # Heads-up: seat 0 is button+SB, seat 1 is BB. Preflop SB acts first.
    seats = [
        {
            "seat_number": 0,
            "user_id": TEST_USER_ID,
            "hole_cards": [_c("A", "spades"), _c("K", "spades")],
            "starting_stack": 10_000,
            "final_stack": 9_700,
            "contributed": 300,
            "is_folded": False,
        },
        {
            "seat_number": 1,
            "user_id": OTHER_USER_ID,
            "hole_cards": [_c("2", "clubs"), _c("7", "diamonds")],
            "starting_stack": 10_000,
            "final_stack": 10_300,
            "contributed": 100,
            "is_folded": False,
        },
    ]
    # Hero (seat 0, SB) calls the BB (pays 50 more to match 100), BB checks,
    # then hero folds on the flop facing a bet. All amounts are the engine's
    # chips-paid delta (holdem convention).
    actions = [
        {"seat_number": 0, "user_id": TEST_USER_ID, "action": "call", "amount": 50, "street": "preflop"},
        {"seat_number": 1, "user_id": OTHER_USER_ID, "action": "check", "amount": 0, "street": "preflop"},
        {"seat_number": 1, "user_id": OTHER_USER_ID, "action": "raise", "amount": 200, "street": "flop"},
        {"seat_number": 0, "user_id": TEST_USER_ID, "action": "fold", "amount": 0, "street": "flop"},
    ]
    hand = await seed_holdem_hand(
        db,
        table.id,
        button_seat=0,
        small_blind=small_blind,
        big_blind=big_blind,
        board=[_c("2", "hearts"), _c("9", "diamonds"), _c("J", "clubs")],
        seats=seats,
        actions=actions,
    )
    return table, hand


# ─── Hold'em per-hand review ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_holdem_hand_review_grades_caller_actions(client, db):
    await seed_user(db, TEST_USER_ID, "hero", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "villain", chip_balance=100_000)
    _table, hand = await _seed_finished_holdem_hand(db)

    resp = await client.get(f"/api/holdem/hands/{hand.id}/review")
    assert resp.status_code == 200
    body = resp.json()

    assert body["hand_id"] == str(hand.id)
    assert body["game"] == "holdem"
    # Hero's own two hole cards are revealed to themselves.
    assert body["your_hole"] == [_c("A", "spades"), _c("K", "spades")]
    # Full board reached.
    assert len(body["board"]) == 3
    # Exactly the caller's own actions appear (call + fold), in order.
    actions = body["actions"]
    assert len(actions) == 2
    assert [a["action"] for a in actions] == ["call", "fold"]
    for a in actions:
        assert a["verdict"] in (
            "best", "good", "inaccuracy", "mistake", "blunder", "no_verdict",
        )
        assert a["confidence_tier"] in ("DETERMINISTIC", "HEURISTIC")


@pytest.mark.asyncio
async def test_holdem_hand_review_excludes_opponent_actions_and_holes(client, db):
    await seed_user(db, TEST_USER_ID, "hero", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "villain", chip_balance=100_000)
    _table, hand = await _seed_finished_holdem_hand(db)

    resp = await client.get(f"/api/holdem/hands/{hand.id}/review")
    assert resp.status_code == 200
    body = resp.json()

    # No opponent actions graded — only the caller's own (call + fold).
    assert len(body["actions"]) == 2

    # Opponent hole cards (2c / 7d) must NOT appear anywhere in the response.
    import json as _json  # noqa: PLC0415

    blob = _json.dumps(body)
    assert '"7"' not in blob or '"diamonds"' not in blob  # villain 7d absent
    # Strong assertion: the only cards present are hero holes + board.
    allowed = {("A", "spades"), ("K", "spades"),
               ("2", "hearts"), ("9", "diamonds"), ("J", "clubs")}
    seen = {(c["value"], c["suit"]) for c in body["your_hole"] + body["board"]}
    assert seen <= allowed


@pytest.mark.asyncio
async def test_holdem_hand_review_non_participant_403(client, db):
    """Caller never held a seat → 403. Hand seated by OTHER_USER only."""
    await seed_user(db, TEST_USER_ID, "intruder", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    table = await seed_holdem_table(db)
    hand = await seed_holdem_hand(
        db,
        table.id,
        seats=[
            {"seat_number": 0, "user_id": OTHER_USER_ID,
             "hole_cards": [_c("A", "hearts"), _c("A", "spades")],
             "starting_stack": 10_000, "final_stack": 10_300},
            {"seat_number": 1, "user_id": OTHER_USER_ID,
             "hole_cards": [_c("K", "hearts"), _c("K", "spades")],
             "starting_stack": 10_000, "final_stack": 9_700},
        ],
        actions=[
            {"seat_number": 0, "user_id": OTHER_USER_ID, "action": "call", "amount": 50},
            {"seat_number": 1, "user_id": OTHER_USER_ID, "action": "check", "amount": 0},
        ],
    )
    resp = await client.get(f"/api/holdem/hands/{hand.id}/review")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_holdem_hand_review_404_for_missing_hand(client, db):
    await seed_user(db, TEST_USER_ID, "wanderer", chip_balance=100_000)
    resp = await client.get("/api/holdem/hands/00000000-0000-0000-0000-000000000000/review")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_holdem_hand_review_chips_to_bb_conversion(client, db):
    """amount_bb uses the table big blind. Hero's call pays 50 chips at bb=100
    → 0.5 bb; the fold pays 0 → 0.0 bb."""
    await seed_user(db, TEST_USER_ID, "hero", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "villain", chip_balance=100_000)
    _table, hand = await _seed_finished_holdem_hand(db, big_blind=100, small_blind=50)

    resp = await client.get(f"/api/holdem/hands/{hand.id}/review")
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    by_action = {a["action"]: a for a in actions}
    assert by_action["call"]["amount_bb"] == pytest.approx(0.5)
    assert by_action["fold"]["amount_bb"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_holdem_hand_review_is_reproducible(client, db):
    """Same hand reviewed twice → identical verdicts + equities (seeded)."""
    await seed_user(db, TEST_USER_ID, "hero", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "villain", chip_balance=100_000)
    _table, hand = await _seed_finished_holdem_hand(db)

    r1 = await client.get(f"/api/holdem/hands/{hand.id}/review")
    r2 = await client.get(f"/api/holdem/hands/{hand.id}/review")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()


# ─── Hold'em table-visit Game Review ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_holdem_table_review_aggregates(client, db):
    await seed_user(db, TEST_USER_ID, "hero", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "villain", chip_balance=100_000)
    table = await seed_holdem_table(db)

    # Two finished hands the hero held a seat in.
    for n in (1, 2):
        await seed_holdem_hand(
            db,
            table.id,
            hand_number=n,
            board=[_c("2", "hearts"), _c("9", "diamonds"), _c("J", "clubs")],
            seats=[
                {"seat_number": 0, "user_id": TEST_USER_ID,
                 "hole_cards": [_c("A", "spades"), _c("K", "spades")],
                 "starting_stack": 10_000, "final_stack": 9_700},
                {"seat_number": 1, "user_id": OTHER_USER_ID,
                 "hole_cards": [_c("2", "clubs"), _c("7", "diamonds")],
                 "starting_stack": 10_000, "final_stack": 10_300},
            ],
            actions=[
                {"seat_number": 0, "user_id": TEST_USER_ID, "action": "call", "amount": 50, "street": "preflop"},
                {"seat_number": 1, "user_id": OTHER_USER_ID, "action": "check", "amount": 0, "street": "preflop"},
                {"seat_number": 1, "user_id": OTHER_USER_ID, "action": "raise", "amount": 200, "street": "flop"},
                {"seat_number": 0, "user_id": TEST_USER_ID, "action": "fold", "amount": 0, "street": "flop"},
            ],
        )

    resp = await client.get(f"/api/holdem/tables/{table.id}/review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "table_visit"
    assert body["game"] == "holdem"
    assert len(body["hands"]) == 2
    assert 0.0 <= body["overall_accuracy"] <= 1.0
    assert body["graded_count"] == sum(h["graded_count"] for h in body["hands"])
    assert body["total_ev_lost_bb"] == pytest.approx(sum(h["ev_lost_bb"] for h in body["hands"]))


@pytest.mark.asyncio
async def test_holdem_table_review_non_participant_403(client, db):
    await seed_user(db, TEST_USER_ID, "intruder", chip_balance=100_000)
    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    table = await seed_holdem_table(db)
    await seed_holdem_hand(
        db,
        table.id,
        seats=[
            {"seat_number": 0, "user_id": OTHER_USER_ID,
             "hole_cards": [_c("A", "hearts"), _c("A", "spades")],
             "starting_stack": 10_000, "final_stack": 10_300},
            {"seat_number": 1, "user_id": OTHER_USER_ID,
             "hole_cards": [_c("K", "hearts"), _c("K", "spades")],
             "starting_stack": 10_000, "final_stack": 9_700},
        ],
        actions=[
            {"seat_number": 0, "user_id": OTHER_USER_ID, "action": "call", "amount": 50},
            {"seat_number": 1, "user_id": OTHER_USER_ID, "action": "check", "amount": 0},
        ],
    )
    resp = await client.get(f"/api/holdem/tables/{table.id}/review")
    assert resp.status_code == 403


# ─── Solo poker endpoints (live deal/act, then review) ────────────────────────


@pytest.mark.asyncio
async def test_solo_poker_hand_review_returns_hand_review(client, db):
    await seed_user(db, TEST_USER_ID, "solo", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 2, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    tid = r.json()["id"]
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    hand_id = deal.json()["current_hand"]["id"]

    # Drive the hand to completion by folding when it's the human's turn.
    for _ in range(8):
        state = (await client.get(f"/api/poker/tournaments/{tid}/state")).json()
        hand = state["current_hand"]
        if hand is None or hand["status"] != "active":
            break
        if hand["current_to_act_seat"] == state["your_seat_number"]:
            await client.post(f"/api/poker/tournaments/{tid}/act", json={"action": "fold", "amount": 0})
            break

    resp = await client.get(f"/api/poker/hands/{hand_id}/review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["game"] == "poker"
    assert body["hand_id"] == hand_id
    assert isinstance(body["actions"], list)
    assert isinstance(body["your_hole"], list)


@pytest.mark.asyncio
async def test_solo_poker_hand_review_non_participant_403(client, db):
    """A solo hand owned by OTHER_USER → TEST_USER gets 403."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.models import PokerHand, PokerHandSeat, PokerSeat, PokerTournament  # noqa: PLC0415

    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    await seed_user(db, TEST_USER_ID, "intruder", chip_balance=100_000)

    t = PokerTournament(
        id=_uuid.uuid4(), bot_count=2, advice_mode="odds", buy_in_cents=1_000,
        starting_stack_chips=1500, hands_per_level=10, seed=42, status="complete",
        button_seat=0, current_hand_number=1, created_at=datetime.now(timezone.utc),
    )
    db.add(t)
    await db.flush()
    db.add(PokerSeat(
        id=_uuid.uuid4(), tournament_id=t.id, user_id=OTHER_USER_ID, seat_number=0,
        archetype_name=None, starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=False, joined_at=datetime.now(timezone.utc),
    ))
    hand = PokerHand(
        id=_uuid.uuid4(), tournament_id=t.id, hand_number=1, button_seat=0,
        seed=42, small_blind=10, big_blind=20, ante=0, board=[], pot_total=30,
        side_pots=[], street="complete", current_bet_to_match=0,
        current_to_act_seat=None, last_aggressor_seat=None, min_raise_increment=20,
        status="complete", result=None, created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    await db.flush()
    db.add(PokerHandSeat(
        id=_uuid.uuid4(), hand_id=hand.id, seat_number=0,
        hole_cards=[{"suit": "spades", "value": "A"}, {"suit": "hearts", "value": "A"}],
        starting_stack=1500, final_stack=1500, contributed=10, current_bet=0,
        is_folded=False, is_all_in=False, has_acted_this_street=True,
    ))
    await db.commit()

    resp = await client.get(f"/api/poker/hands/{hand.id}/review")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_solo_tournament_review_is_game_review_shape(client, db):
    """The upgraded tournament endpoint returns the unified GameReview shape."""
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
    # Unified GameReview shape (NOT the old PokerSessionReviewOut shape).
    assert body["scope"] == "tournament"
    assert body["game"] == "poker"
    assert "overall_accuracy" in body
    assert "total_ev_lost_bb" in body
    assert "graded_count" in body
    assert isinstance(body["hands"], list)
    # Old fields are gone.
    assert "total_actions" not in body
    assert "deterministic_actions" not in body


@pytest.mark.asyncio
async def test_solo_tournament_review_non_participant_403(client, db):
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.models import PokerSeat, PokerTournament  # noqa: PLC0415

    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    await seed_user(db, TEST_USER_ID, "intruder", chip_balance=100_000)
    t = PokerTournament(
        id=_uuid.uuid4(), bot_count=2, advice_mode="odds", buy_in_cents=1_000,
        starting_stack_chips=1500, hands_per_level=10, seed=42, status="active",
        button_seat=0, current_hand_number=0, created_at=datetime.now(timezone.utc),
    )
    db.add(t)
    await db.flush()
    db.add(PokerSeat(
        id=_uuid.uuid4(), tournament_id=t.id, user_id=OTHER_USER_ID, seat_number=0,
        archetype_name=None, starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=False, joined_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    resp = await client.get(f"/api/poker/tournaments/{t.id}/review")
    assert resp.status_code == 403
