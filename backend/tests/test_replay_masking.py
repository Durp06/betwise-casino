"""
test_replay_masking.py — regression test for P6 (mid-hand hole-card leak).

P6: GET /api/poker/hands/{hand_id}/replay returned EVERY seat's hole_cards
unmasked, even while the hand was still in progress (status != 'complete').
That leaks opponents' (bots') hole cards to a player who is still in the hand —
a cheating vector. The fix mirrors _build_state_payload's masking: while the
hand is NOT complete, any seat whose user_id != the requester is masked to
[None, None]; the requester still sees their own cards; finished hands stay
public (non-folded cards revealed at showdown).

These tests assert the CORRECT post-fix behavior. They will FAIL against the
pre-fix code (which leaks) and PASS once _get_hand_replay masks opponents
during play.

Style: pytest-asyncio + in-memory SQLite via conftest fixtures (client / db,
seed_user, dev-bypass current_user = TEST_USER_ID).
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest

from backend.tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_user,
)

# Deterministic sample cards used by the directly-seeded hands.
_HUMAN_HOLE = [{"suit": "spades", "value": "A"}, {"suit": "hearts", "value": "A"}]
_BOT_HOLE = [{"suit": "clubs", "value": "K"}, {"suit": "diamonds", "value": "K"}]


def _is_masked(hole: list) -> bool:
    """A masked hole-card list is exactly two None entries."""
    return hole == [None, None]


async def _seed_active_hand_two_seats(
    db,
    *,
    human_user_id: _uuid.UUID,
    hand_status: str,
    human_folded: bool = False,
    bot_folded: bool = False,
):
    """Seed a tournament with a human seat (0) + a bot seat (1) and one hand.

    Returns (tournament, hand). The hand's status is `hand_status`; seat 0's
    hole cards are _HUMAN_HOLE, seat 1's are _BOT_HOLE.
    """
    from backend.models import (  # noqa: PLC0415
        PokerHand,
        PokerHandSeat,
        PokerSeat,
        PokerTournament,
    )

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
        current_hand_number=1,
        created_at=datetime.now(timezone.utc),
    )
    db.add(t)
    await db.flush()

    db.add(PokerSeat(
        id=_uuid.uuid4(), tournament_id=t.id, user_id=human_user_id,
        seat_number=0, archetype_name=None,
        starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=False,
        joined_at=datetime.now(timezone.utc),
    ))
    db.add(PokerSeat(
        id=_uuid.uuid4(), tournament_id=t.id, user_id=None,
        seat_number=1, archetype_name="tag",
        starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=True,
        joined_at=datetime.now(timezone.utc),
    ))

    hand = PokerHand(
        id=_uuid.uuid4(),
        tournament_id=t.id, hand_number=1, button_seat=0,
        seed=42, small_blind=10, big_blind=20, ante=0,
        board=[], pot_total=30, side_pots=[],
        street="preflop", current_bet_to_match=20,
        current_to_act_seat=0, last_aggressor_seat=None,
        min_raise_increment=20, status=hand_status, result=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    await db.flush()

    db.add(PokerHandSeat(
        id=_uuid.uuid4(), hand_id=hand.id, seat_number=0,
        hole_cards=_HUMAN_HOLE,
        starting_stack=1500, final_stack=1490, contributed=10, current_bet=10,
        is_folded=human_folded, is_all_in=False, has_acted_this_street=False,
    ))
    db.add(PokerHandSeat(
        id=_uuid.uuid4(), hand_id=hand.id, seat_number=1,
        hole_cards=_BOT_HOLE,
        starting_stack=1500, final_stack=1480, contributed=20, current_bet=20,
        is_folded=bot_folded, is_all_in=False, has_acted_this_street=False,
    ))
    await db.commit()
    return t, hand


# ─── Direct-seed tests (deterministic, fast) ──────────────────────────────────


@pytest.mark.asyncio
async def test_replay_masks_opponent_hole_cards_while_active(client, db):
    """P6 — requesting the replay of an ACTIVE hand must mask the opponent
    (bot) hole cards while revealing the requester's own."""
    await seed_user(db, TEST_USER_ID, "human", chip_balance=100_000)
    _, hand = await _seed_active_hand_two_seats(
        db, human_user_id=TEST_USER_ID, hand_status="active",
    )

    resp = await client.get(f"/api/poker/hands/{hand.id}/replay")
    assert resp.status_code == 200
    body = resp.json()

    seats = {s["seat_number"]: s for s in body["seats"]}
    # Requester (seat 0) sees their own cards.
    assert seats[0]["hole_cards"] == _HUMAN_HOLE
    # Opponent bot (seat 1) is masked during play.
    assert _is_masked(seats[1]["hole_cards"]), (
        f"P6 leak: opponent hole cards exposed during active hand: "
        f"{seats[1]['hole_cards']!r}"
    )


@pytest.mark.asyncio
async def test_replay_reveals_all_hole_cards_when_complete(client, db):
    """P6 — once the hand is complete, hole cards are public (non-folded seats
    revealed at showdown). Both seats' real cards must come through."""
    await seed_user(db, TEST_USER_ID, "human", chip_balance=100_000)
    _, hand = await _seed_active_hand_two_seats(
        db, human_user_id=TEST_USER_ID, hand_status="complete",
    )

    resp = await client.get(f"/api/poker/hands/{hand.id}/replay")
    assert resp.status_code == 200
    body = resp.json()

    seats = {s["seat_number"]: s for s in body["seats"]}
    assert seats[0]["hole_cards"] == _HUMAN_HOLE
    # Non-folded opponent cards are revealed after showdown.
    assert seats[1]["hole_cards"] == _BOT_HOLE
    assert not _is_masked(seats[1]["hole_cards"])


@pytest.mark.asyncio
async def test_replay_masks_for_non_participant_self_seat_too_when_active(client, db):
    """Defense-in-depth: an active hand owned by ANOTHER user is gated by the
    existing 403 authorization, so a non-participant never sees any cards.

    (The 403 path is the first line of defense; the masking is the second.
    This pins the existing behavior so the P6 masking change doesn't
    accidentally loosen the participant gate.)"""
    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    await seed_user(db, TEST_USER_ID, "intruder", chip_balance=100_000)
    _, hand = await _seed_active_hand_two_seats(
        db, human_user_id=OTHER_USER_ID, hand_status="active",
    )

    # TEST_USER (the dev-bypass current_user) is NOT a participant.
    resp = await client.get(f"/api/poker/hands/{hand.id}/replay")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_replay_complete_hand_is_public_to_non_participant(client, db):
    """A COMPLETE hand's replay is public (per spec: public after showdown),
    so even a non-participant can fetch it and see revealed cards."""
    await seed_user(db, OTHER_USER_ID, "owner", chip_balance=100_000)
    await seed_user(db, TEST_USER_ID, "spectator", chip_balance=100_000)
    _, hand = await _seed_active_hand_two_seats(
        db, human_user_id=OTHER_USER_ID, hand_status="complete",
    )

    resp = await client.get(f"/api/poker/hands/{hand.id}/replay")
    assert resp.status_code == 200
    body = resp.json()
    seats = {s["seat_number"]: s for s in body["seats"]}
    # Public after showdown — both real hands visible.
    assert seats[0]["hole_cards"] == _HUMAN_HOLE
    assert seats[1]["hole_cards"] == _BOT_HOLE


# ─── End-to-end deal test (exercises the real deal path) ──────────────────────


@pytest.mark.asyncio
async def test_replay_via_dealt_hand_masks_bots(client, db):
    """P6 end-to-end — create a tournament + deal via the public endpoints,
    then GET the replay of the live hand and assert bot seats are masked while
    the human sees their own two cards."""
    await seed_user(db, TEST_USER_ID, "dealer", chip_balance=100_000)
    r = await client.post(
        "/api/poker/tournaments",
        json={"bot_count": 3, "advice_mode": "odds", "buy_in_cents": 1_000, "starting_stack_chips": 1500},
    )
    assert r.status_code == 201
    tid = r.json()["id"]

    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    assert deal.status_code == 200
    hand = deal.json()["current_hand"]
    assert hand is not None
    hand_id = hand["id"]

    # Only run the masking assertion while the hand is still active. If the
    # deal somehow auto-completed (it should not — no human acted), the public
    # reveal is correct and there is nothing to leak.
    if hand["status"] != "active":
        pytest.skip("dealt hand auto-completed; nothing to mask")

    replay = await client.get(f"/api/poker/hands/{hand_id}/replay")
    assert replay.status_code == 200
    seats = replay.json()["seats"]

    me = next(s for s in seats if s["seat_number"] == 0)
    others = [s for s in seats if s["seat_number"] != 0]

    # Human sees own cards.
    assert len(me["hole_cards"]) == 2
    for c in me["hole_cards"]:
        assert c is not None
        assert "suit" in c and "value" in c

    # Every opponent seat is masked during the active hand.
    assert others, "expected at least one bot seat"
    for opp in others:
        assert _is_masked(opp["hole_cards"]), (
            f"P6 leak: seat {opp['seat_number']} exposed during active hand: "
            f"{opp['hole_cards']!r}"
        )
