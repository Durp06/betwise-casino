"""test_poker_bust_handling.py — regression tests for the solo-poker crash/stall
that happens once a player busts.

Bug: `poker_game.py::_deal_or_continue_hand` builds the betting state from
`starting_stacks = [s.current_stack for s in seats]` INCLUDING busted (0-chip)
seats and creates `PokerHandSeat` rows for them with empty hole_cards. The
engine treats a 0-chip seat as live (not folded / not all-in), so `next_to_act`
can put a busted seat on turn:
  - busted HUMAN → POST /act 500s at `_hand_str_for_seat` (IndexError on empty
    hole_cards);
  - busted BOT → `_drive_bot_actions` stalls re-acting a bet it can't match.

The fix folds busted seats out of every dealt hand and ends the tournament once
the human busts. These tests pin that.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest

from backend.models import PokerSeat, PokerTournament
from backend.tests.conftest import TEST_USER_ID, seed_user


async def _seed_tournament(db, seats_spec: list[dict], *, seed: int = 777, button_seat: int = 0) -> str:
    """seats_spec: list of dicts per seat, in seat order. Each:
    {stack, bust(bool), bot(bool), archetype(str|None)}. Seat 0 is the human."""
    await seed_user(db, TEST_USER_ID, "buster", chip_balance=10_000_000)
    tid = _uuid.uuid4()
    n_bots = sum(1 for s in seats_spec if s.get("bot"))
    db.add(PokerTournament(
        id=tid, bot_count=n_bots, advice_mode="odds", buy_in_cents=1_000,
        starting_stack_chips=1500, hands_per_level=10, seed=seed, status="active",
        button_seat=button_seat, current_hand_number=0, created_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    for i, spec in enumerate(seats_spec):
        db.add(PokerSeat(
            id=_uuid.uuid4(), tournament_id=tid,
            user_id=None if spec.get("bot") else TEST_USER_ID,
            seat_number=i, archetype_name=spec.get("archetype"),
            starting_stack=1500, current_stack=spec["stack"],
            is_bust=spec.get("bust", False), is_bot=spec.get("bot", False),
            joined_at=datetime.now(timezone.utc),
        ))
    await db.commit()
    return str(tid)


@pytest.mark.asyncio
async def test_deal_with_busted_bot_does_not_put_it_on_turn_or_stall(client, db):
    """A busted BOT (0 chips) must be folded out of the next hand — never put on
    turn, never stalls the action. Button placed so the busted bot would be UTG
    under the old (bust-as-live) logic."""
    # seats: 0=human(live), 1=bot BUSTED, 2=bot(live), 3=bot(live)
    # button=2 → SB=3, BB=0(human), UTG=1(the busted bot under old turn order)
    tid = await _seed_tournament(
        db,
        [
            {"stack": 1500, "bot": False},
            {"stack": 0, "bot": True, "bust": True, "archetype": "TAG"},
            {"stack": 1500, "bot": True, "archetype": "LAG"},
            {"stack": 1500, "bot": True, "archetype": "CallingStation"},
        ],
        button_seat=2,
    )
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    assert deal.status_code == 200
    hand = deal.json()["current_hand"]
    assert hand is not None
    # The busted bot (seat 1) is never the actor and is folded in the hand.
    assert hand["current_to_act_seat"] != 1, "busted bot was put on turn (stall)"
    seat1 = next(s for s in hand["seats"] if s["seat_number"] == 1)
    assert seat1["is_folded"] is True, "busted seat should be folded out of the hand"
    # It must be folded STRUCTURALLY (out before the action), not by making a
    # live decision: a busted seat should never be handed a turn to act at all.
    decisions = [
        a for a in hand["actions"]
        if a["seat_number"] == 1 and a["action"] not in ("post_blind", "post_ante")
    ]
    assert not decisions, f"busted bot was handed a turn and acted: {[d['action'] for d in decisions]}"


@pytest.mark.asyncio
async def test_deal_when_human_busted_ends_tournament_cleanly(client, db):
    """Once the HUMAN is busted, dealing must NOT crash and must end the
    tournament (the human's session is over) instead of dealing them in with
    empty hole cards."""
    # human(seat 0) busted; 3 bots still have chips
    tid = await _seed_tournament(
        db,
        [
            {"stack": 0, "bot": False, "bust": True},
            {"stack": 1500, "bot": True, "archetype": "TAG"},
            {"stack": 1500, "bot": True, "archetype": "LAG"},
            {"stack": 1500, "bot": True, "archetype": "Nit"},
        ],
        button_seat=1,
    )
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    assert deal.status_code == 200  # no 500
    assert deal.json()["tournament"]["status"] == "complete"


@pytest.mark.asyncio
async def test_play_until_human_busts_never_500s(client, db):
    """Faithful reproduction of the reported crash: a short-stacked human who
    keeps calling busts within a few hands. Under the old code the next deal put
    the busted human on turn and /act 500'd. The whole session must stay 500-free
    and end with the human busted."""
    # Human starts with 2bb so auto-calling busts them fast; bots are deep.
    tid = await _seed_tournament(
        db,
        [
            {"stack": 40, "bot": False},
            {"stack": 1500, "bot": True, "archetype": "Maniac"},
            {"stack": 1500, "bot": True, "archetype": "LAG"},
            {"stack": 1500, "bot": True, "archetype": "TAG"},
        ],
        seed=4242,
    )
    statuses: list[int] = []

    async def _post(url, body=None):
        r = await client.post(url, json=body) if body is not None else await client.post(url)
        statuses.append(r.status_code)
        return r

    human_busted = False
    for _ in range(12):
        deal = await _post(f"/api/poker/tournaments/{tid}/deal")
        body = deal.json() if deal.status_code == 200 else {}
        if body.get("tournament", {}).get("status") == "complete":
            # Did the human bust out?
            human = next((s for s in body.get("seats", []) if not s["is_bot"]), None)
            human_busted = bool(human and human["is_bust"])
            break
        hand = body.get("current_hand")
        for _ in range(12):
            if not hand or hand["status"] != "active" or hand["current_to_act_seat"] != 0:
                break
            me = next(s for s in hand["seats"] if s["seat_number"] == 0)
            to_call = hand["current_bet_to_match"] - me["current_bet"]
            act = "check" if to_call <= 0 else "call"
            r = await _post(f"/api/poker/tournaments/{tid}/act", {"action": act, "amount": 0})
            hand = r.json().get("current_hand") if r.status_code == 200 else None

    assert 500 not in statuses, f"a request 500'd during a busting session: {statuses}"
    assert human_busted, "test did not actually drive the human to bust"
