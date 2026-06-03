"""test_poker_bot_aggression.py — regression tests for the "solo bots fold every
hand" bug.

Root cause (pre-fix): `_preflop_decision` treated the unraised big blind as a
bet to fold to, so every bot routed into its fold-to-a-raise logic and the
open-raise path was unreachable. Bots open-raised ~7% of the time and folded
~84% preflop, so the human almost never got a played hand. Two related leaks:
a bot facing NO bet folded for free (the BB), and a made hand postflop folded
unconditionally to any pot-sized bet.

These tests pin the corrected behavior. They are written against the public
`decide()` so they exercise exactly what the router calls.
"""
from __future__ import annotations

import random

import pytest

from backend.game.poker.archetypes import (
    ARCHETYPE_REGISTRY,
    ArchetypeContext,
    _opening_range,
    decide,
)
from backend.game.poker.cards import parse_card
from backend.tests.conftest import TEST_USER_ID, seed_user


def C(s):
    return parse_card(s)


def _ctx(
    hole=("As", "Kh"),
    board=(),
    street="preflop",
    position="MP",
    stack_bb=40.0,
    pot_bb=1.5,
    to_call_bb=1.0,
    n_live_opponents=2,
):
    return ArchetypeContext(
        hole=(C(hole[0]), C(hole[1])),
        board=tuple(C(s) for s in board),
        street=street,
        position=position,
        stack_bb=stack_bb,
        pot_bb=pot_bb,
        to_call_bb=to_call_bb,
        n_live_opponents=n_live_opponents,
    )


def _a_non_premium_open(spec) -> str:
    """A hand inside the archetype's opening range that is NOT a groups-1-2
    premium — so the buggy code (which only ever *3-bets* premiums when it
    thinks it faces a bet) would never raise it, but the fixed open logic will.
    """
    from backend.game.poker.ranges import union_of_groups  # noqa: PLC0415

    premium = union_of_groups(1, 2)
    # Prefer a recognizable middle pair / strong broadway if it's in range.
    for candidate in ("99", "AQo", "ATs", "KJs", "88", "AJo"):
        if candidate in _opening_range(spec) and candidate not in premium:
            return candidate
    # Fallback: any opening hand that isn't premium.
    for h in _opening_range(spec):
        if h not in premium:
            return h
    raise AssertionError("no non-premium opening hand found")


def _hole_for_hand(hand: str) -> tuple[str, str]:
    """Map a canonical hand string to two concrete cards (suit-disambiguated)."""
    if len(hand) == 2:  # pair
        return (f"{hand[0]}s", f"{hand[1]}h")
    hi, lo, suited = hand[0], hand[1], hand[2]
    return (f"{hi}s", f"{lo}s") if suited == "s" else (f"{hi}s", f"{lo}h")


# ─── Preflop: bots OPEN their range in an unraised pot ────────────────────────


def test_bot_opens_non_premium_range_hand_in_unraised_pot():
    """A TAG in an UNRAISED pot (the only chips in are the blinds → to_call is
    one big blind) must OPEN-RAISE a hand in its opening range, not fold/limp it.

    Pre-fix: to_call_bb==1.0 was read as 'facing a bet', so a non-premium open
    hand was at best flat-called and usually folded — never raised. This is the
    core 'bots never enter the pot' bug.
    """
    spec = ARCHETYPE_REGISTRY["TAG"]
    hand = _a_non_premium_open(spec)
    hole = _hole_for_hand(hand)
    ctx = _ctx(hole=hole, to_call_bb=1.0, stack_bb=40)
    # Deterministic given a seed; assert it raises for every seed (an open is
    # not a coin-flip for a TAG with a clear opening hand).
    actions = {decide(spec, ctx, random.Random(seed)).action for seed in range(15)}
    assert actions == {"raise"}, (
        f"TAG should OPEN-RAISE {hand} in an unraised pot; got {actions}"
    )


def test_table_of_bots_enters_pots_at_a_playable_rate():
    """Across many random hands in an unraised pot, bots must voluntarily put
    money in (raise or call) at roughly their VPIP — NOT fold ~85% of the time.

    Pre-fix this aggregate VPIP collapsed to ~15% (the human could never get a
    hand). We assert a sane floor: at least 25% of decisions are non-folds.
    """
    from backend.game.poker.ranges import ALL_HANDS  # noqa: PLC0415

    spec = ARCHETYPE_REGISTRY["LAG"]  # VPIP 0.30 — should be active
    non_fold = 0
    total = 0
    rng = random.Random(7)
    for hand in ALL_HANDS:
        hole = _hole_for_hand(hand)
        ctx = _ctx(hole=hole, to_call_bb=1.0, stack_bb=40)
        d = decide(spec, ctx, rng)
        total += 1
        if d.action != "fold":
            non_fold += 1
    rate = non_fold / total
    assert rate >= 0.25, f"LAG entered only {rate:.0%} of unraised pots (too tight)"


# ─── Preflop: a bot facing NO bet checks for free, never folds ────────────────


def test_bot_facing_no_bet_checks_instead_of_folding():
    """A bot in the big blind (to_call_bb == 0) with junk must CHECK for a free
    flop — never fold a hand it is already all-in-the-blind on.

    The router hardcodes position='MP' for bots, so the old `position == 'BB'`
    guard never fired and the BB bot folded for free. Use position='MP' here to
    reproduce exactly what the router passes.
    """
    spec = ARCHETYPE_REGISTRY["Nit"]
    ctx = _ctx(hole=("7s", "2c"), position="MP", to_call_bb=0.0, stack_bb=40)
    for seed in range(15):
        d = decide(spec, ctx, random.Random(seed))
        assert d.action != "fold", "a bot facing no bet must never fold (check is free)"
    assert decide(spec, ctx, random.Random(0)).action == "check"


# ─── Postflop: a made hand does not auto-fold to a normal bet ─────────────────


def test_made_hand_does_not_autofold_to_cbet():
    """Top pair facing a ~pot-sized c-bet (pot_odds >= 0.35) must not fold every
    time. Pre-fix, a 'medium' made hand with pot_odds >= 0.35 fell through to an
    unconditional fold, so bots folded every pair to a standard c-bet.
    """
    spec = ARCHETYPE_REGISTRY["TAG"]
    ctx = _ctx(
        hole=("Ks", "5c"),
        board=("Kh", "8d", "3c"),  # top pair (medium made hand)
        street="flop",
        to_call_bb=3.0,
        pot_bb=4.0,  # pot_odds = 3/(4+3) = 0.43 >= 0.35
    )
    non_folds = sum(
        1 for seed in range(20)
        if decide(spec, ctx, random.Random(seed)).action != "fold"
    )
    assert non_folds >= 5, (
        f"TAG folded top pair to a c-bet {20 - non_folds}/20 times — made hands "
        "should defend at least sometimes"
    )


# ─── End-to-end: bots actually play through the real /deal + /act endpoints ───


async def _play_hand_observing(client, tid):
    """Deal a hand; the human (seat 0) checks when it's free and CALLS when
    facing a bet, so the human stays in and the hand reaches a flop with the
    bots. The session early-exits after a couple of hands (see the test), so the
    human never commits enough to bust — keeping this test clear of the separate
    busted-seat bug. Returns (hand, status)."""
    deal = await client.post(f"/api/poker/tournaments/{tid}/deal")
    body = deal.json()
    hand = body["current_hand"]
    status = body["tournament"]["status"]
    for _ in range(60):
        if hand is None or hand["status"] != "active" or hand["current_to_act_seat"] != 0:
            break
        me = next(s for s in hand["seats"] if s["seat_number"] == 0)
        to_call = hand["current_bet_to_match"] - me["current_bet"]
        action = "check" if to_call <= 0 else "call"
        resp = await client.post(
            f"/api/poker/tournaments/{tid}/act", json={"action": action, "amount": 0}
        )
        if resp.status_code != 200:
            break
        body = resp.json()
        hand = body["current_hand"]
        status = body["tournament"]["status"]
    return hand, status


async def _seed_solo_tournament(db, seed: int, archetypes: list[str]) -> str:
    """Seed a deterministic solo tournament directly in the DB (the create
    endpoint randomizes seed + archetypes, which makes card outcomes flaky under
    pytest-randomly). Fixed seed + fixed archetypes → fully reproducible hands."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.models import PokerSeat, PokerTournament  # noqa: PLC0415

    await seed_user(db, TEST_USER_ID, "grinder", chip_balance=10_000_000)
    tid = _uuid.uuid4()
    db.add(PokerTournament(
        id=tid, bot_count=len(archetypes), advice_mode="odds", buy_in_cents=1_000,
        starting_stack_chips=1500, hands_per_level=10, seed=seed, status="active",
        button_seat=0, current_hand_number=0, created_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    db.add(PokerSeat(
        id=_uuid.uuid4(), tournament_id=tid, user_id=TEST_USER_ID, seat_number=0,
        archetype_name=None, starting_stack=1500, current_stack=1500,
        is_bust=False, is_bot=False, joined_at=datetime.now(timezone.utc),
    ))
    for i, name in enumerate(archetypes, start=1):
        db.add(PokerSeat(
            id=_uuid.uuid4(), tournament_id=tid, user_id=None, seat_number=i,
            archetype_name=name, starting_stack=1500, current_stack=1500,
            is_bust=False, is_bot=True, joined_at=datetime.now(timezone.utc),
        ))
    await db.commit()
    return str(tid)


@pytest.mark.asyncio
async def test_bots_play_real_hands_and_reach_flops(client, db):
    """Regression for 'solo bots fold every time', exercised through the REAL
    /deal + /act endpoints (so the router's ArchetypeContext construction is in
    the loop, not just decide()). Hands must reach a flop and bots must
    voluntarily enter pots (open-raise / check the big blind). Pre-fix this was
    impossible — bots folded ~85% preflop and the BB folded for free, so hands
    ended preflop and the human never got to play.

    Deterministic: fixed seed + fixed loose-ish archetypes so the assertion is
    stable. The human folds to bets (only blinds bleed) so the session never
    busts the human — keeping this test clear of the separate busted-seat bug."""
    tid = await _seed_solo_tournament(db, seed=20260603, archetypes=["LAG", "CallingStation", "TAG"])

    seen_hand_ids: set[str] = set()
    flops = 0
    bot_voluntary = 0  # open-raises + big-blind checks (both impossible pre-fix)

    for _ in range(8):
        hand, status = await _play_hand_observing(client, tid)
        if hand is None or hand["id"] in seen_hand_ids:
            break
        seen_hand_ids.add(hand["id"])
        if len(hand["board"]) >= 3:
            flops += 1
        for a in hand["actions"]:
            if a["is_human"]:
                continue
            if a["action"] == "raise" or (a["action"] == "check" and a["street"] == "preflop"):
                bot_voluntary += 1
        if flops >= 2 and bot_voluntary >= 1:
            break  # enough evidence — stop early, well before anyone busts
        if status == "complete":
            break

    hands_played = len(seen_hand_ids)
    assert hands_played >= 2, f"only {hands_played} hands played"
    assert flops >= 2, (
        f"only {flops}/{hands_played} hands reached a flop — bots still fold preflop"
    )
    assert bot_voluntary >= 1, (
        "no bot ever open-raised or checked the big blind across the session"
    )
