"""
test_ev_engine.py — Unit tests for the infinite-deck H17 EV engine.

Acceptance criteria: AC-B-EV1 through AC-B-EV9 (specs/blackjack-study.md).

Module under test: backend.game.blackjack.ev  (does NOT exist yet — every test
in this file will fail with ImportError until the implementer creates ev.py).

Card representation follows CLAUDE.md / engine.py conventions:
  {"suit": <suit_string>, "value": <value_string>}
Values: "2".."10", "J", "Q", "K", "A"
"""

from __future__ import annotations

import asyncio
import inspect
import types

import pytest


# ─── card / hand builder helpers ─────────────────────────────────────────────

def _c(value: str, suit: str = "hearts") -> dict:
    """Build a minimal card dict."""
    return {"suit": suit, "value": value}


def _hard_hand(total: int) -> list[dict]:
    """Return a 2-card hard hand summing to `total` (5 ≤ total ≤ 20).

    Uses a ten-card (value "10") as the first card when total > 11, otherwise
    two small cards.  The result has no ace, so is_soft will be False.
    """
    assert 4 <= total <= 20, f"Cannot build 2-card hard hand for total {total}"
    if total <= 11:
        first, second = total - 2, 2
        return [_c(str(first)), _c(str(second))]
    # e.g. total=16 → [10, 6]
    second = total - 10
    assert 2 <= second <= 10, f"Cannot split hard {total} as 10+{second}"
    return [_c("10"), _c(str(second))]


def _soft_hand(total: int) -> list[dict]:
    """Return a 2-card soft hand summing to `total` (13 ≤ total ≤ 21).

    Ace (11) + (total - 11) produces the right soft total.
    """
    assert 13 <= total <= 21, f"Cannot build 2-card soft hand for total {total}"
    second_val = total - 11
    # Map int to card value string
    if second_val == 10:
        second_str = "10"
    else:
        second_str = str(second_val)
    return [_c("A"), _c(second_str)]


# All upcard values in order (used by parametrize sweeps)
ALL_UPCARDS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]


# ─── AC-B-EV1: purity ────────────────────────────────────────────────────────

def test_ev_module_is_pure_no_async_no_random_no_sqlalchemy() -> None:
    """AC-B-EV1: ev.py is pure-sync — no async defs, no import random, no sqlalchemy."""
    # This test will ImportError until ev.py is created, which is the intended red state.
    import backend.game.blackjack.ev as ev_module  # type: ignore[import]

    # 1. No async callables exported from the module
    for name, obj in inspect.getmembers(ev_module):
        if callable(obj) and inspect.iscoroutinefunction(obj):
            pytest.fail(f"ev.py must have no async functions; found async def {name}()")

    # 2. No 'import random' or 'import sqlalchemy' in the module's source
    source_file = inspect.getfile(ev_module)
    with open(source_file, encoding="utf-8") as fh:
        source = fh.read()
    assert "import random" not in source, "ev.py must not import random"
    assert "import sqlalchemy" not in source, "ev.py must not import sqlalchemy"
    assert "async def" not in source, "ev.py must have no async def"


# ─── AC-B-EV2: dealer_outcome_distribution ───────────────────────────────────

@pytest.mark.parametrize("upcard_value", ALL_UPCARDS)
def test_dealer_outcome_distribution_sums_to_one(upcard_value: str) -> None:
    """AC-B-EV2: dealer_outcome_distribution sums to 1.0 (within 1e-9) for every upcard."""
    from backend.game.blackjack.ev import dealer_outcome_distribution  # type: ignore[import]

    upcard = _c(upcard_value)
    dist = dealer_outcome_distribution(upcard)

    # Required keys
    expected_keys = {17, 18, 19, 20, 21, "bust"}
    assert set(dist.keys()) == expected_keys, (
        f"dealer_outcome_distribution keys must be {expected_keys}; got {set(dist.keys())}"
    )

    total = sum(dist.values())
    assert abs(total - 1.0) < 1e-9, (
        f"dealer_outcome_distribution sums to {total!r} for upcard {upcard_value}; must equal 1.0"
    )


def test_dealer_bust_pct_weak_upcard_higher_than_strong() -> None:
    """AC-B-EV2: dealer 6 busts more often than dealer A (basic-strategy intuition)."""
    from backend.game.blackjack.ev import dealer_outcome_distribution  # type: ignore[import]

    dist_6 = dealer_outcome_distribution(_c("6"))
    dist_a = dealer_outcome_distribution(_c("A"))

    assert dist_6["bust"] > dist_a["bust"], (
        f"Dealer showing 6 should bust more than dealer showing A; "
        f"got dist_6['bust']={dist_6['bust']:.4f}, dist_A['bust']={dist_a['bust']:.4f}"
    )


# ─── AC-B-EV3: ev_stand ──────────────────────────────────────────────────────

@pytest.mark.parametrize("upcard_value", ALL_UPCARDS)
def test_ev_stand_20_is_strongly_positive_all_upcards(upcard_value: str) -> None:
    """AC-B-EV3: ev_stand(20, False, upcard) > 0.4 for every dealer upcard."""
    from backend.game.blackjack.ev import ev_stand  # type: ignore[import]

    ev = ev_stand(20, False, _c(upcard_value))
    assert ev > 0.4, (
        f"ev_stand(20, is_soft=False) vs dealer {upcard_value} should be > 0.4; got {ev:.4f}"
    )


def test_ev_stand_hard_16_vs_ten_is_strongly_negative() -> None:
    """AC-B-EV3: ev_stand(16, False, 10) < -0.4."""
    from backend.game.blackjack.ev import ev_stand  # type: ignore[import]

    ev = ev_stand(16, False, _c("10"))
    assert ev < -0.4, (
        f"ev_stand(16, is_soft=False) vs dealer 10 should be < -0.4; got {ev:.4f}"
    )


def test_ev_stand_returns_float_in_range() -> None:
    """AC-B-EV3: ev_stand always returns a float in [-1, 1]."""
    from backend.game.blackjack.ev import ev_stand  # type: ignore[import]

    for total in range(4, 22):
        for upcard_value in ALL_UPCARDS:
            ev = ev_stand(total, False, _c(upcard_value))
            assert isinstance(ev, float), f"ev_stand returned {type(ev)} not float"
            assert -1.0 <= ev <= 1.0, (
                f"ev_stand({total}, False, {upcard_value}) = {ev:.4f} is outside [-1, 1]"
            )


# ─── AC-B-EV4: action_evs key-presence rules ─────────────────────────────────

def test_action_evs_always_contains_hit_and_stand() -> None:
    """AC-B-EV4: action_evs always includes 'hit' and 'stand' keys."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("10"), _c("6")]  # hard 16
    result = action_evs(hand, _c("9"), can_double=False, can_split=False)
    assert "hit" in result, "action_evs must always include 'hit'"
    assert "stand" in result, "action_evs must always include 'stand'"


def test_action_evs_double_only_on_two_cards() -> None:
    """AC-B-EV4: 'double' key present iff len(hand_cards) == 2."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    two_card_hand = [_c("6"), _c("5")]  # hard 11
    three_card_hand = [_c("2"), _c("4"), _c("5")]  # hard 11, 3 cards

    result_2 = action_evs(two_card_hand, _c("7"), can_double=True, can_split=False)
    result_3 = action_evs(three_card_hand, _c("7"), can_double=False, can_split=False)

    assert "double" in result_2, "action_evs must include 'double' for a 2-card hand (can_double=True)"
    assert "double" not in result_3, "action_evs must NOT include 'double' for a 3-card hand"


def test_action_evs_never_contains_split_key() -> None:
    """AC-B-EV4: 'split' key is never in action_evs (split EV omitted in v1)."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    # Even a splittable pair should not return a split EV
    pair_hand = [_c("8"), _c("8", "spades")]
    result = action_evs(pair_hand, _c("9"), can_double=True, can_split=True)
    assert "split" not in result, (
        "action_evs must NEVER include a 'split' key (split EV is deferred to v2)"
    )


def test_best_action_ev_returns_argmax_action_and_value() -> None:
    """AC-B-EV4: best_action_ev returns (action, ev) for the argmax over action_evs."""
    from backend.game.blackjack.ev import action_evs, best_action_ev  # type: ignore[import]

    hand = [_c("6"), _c("5")]  # hard 11
    upcard = _c("6")
    evs = action_evs(hand, upcard, can_double=True, can_split=False)
    best_act, best_val = best_action_ev(hand, upcard, can_double=True, can_split=False)

    assert best_act in evs, f"best_action_ev returned action '{best_act}' not in action_evs keys {set(evs)}"
    assert best_val == pytest.approx(max(evs.values()), abs=1e-9), (
        f"best_action_ev value {best_val:.6f} does not match max(action_evs) {max(evs.values()):.6f}"
    )
    assert best_act == max(evs, key=evs.__getitem__), (
        f"best_action_ev returned '{best_act}' but argmax of action_evs is '{max(evs, key=evs.__getitem__)}'"
    )


# ─── AC-B-EV5: Sharp-set anchor orderings ────────────────────────────────────

def test_ev5_hard16_vs_10_hit_beats_stand() -> None:
    """AC-B-EV5: hard 16 vs 10 → ev(hit) > ev(stand)."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("10"), _c("6")]
    evs = action_evs(hand, _c("10"), can_double=False, can_split=False)
    assert evs["hit"] > evs["stand"], (
        f"hard 16 vs 10: hit EV {evs['hit']:.4f} should beat stand EV {evs['stand']:.4f}"
    )


@pytest.mark.parametrize("dealer_value", ["4", "5", "6"])
def test_ev5_hard12_vs_4_5_6_stand_beats_hit(dealer_value: str) -> None:
    """AC-B-EV5: hard 12 vs 4/5/6 → ev(stand) > ev(hit)."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("7"), _c("5")]  # hard 12
    evs = action_evs(hand, _c(dealer_value), can_double=False, can_split=False)
    assert evs["stand"] > evs["hit"], (
        f"hard 12 vs {dealer_value}: stand EV {evs['stand']:.4f} should beat hit EV {evs['hit']:.4f}"
    )


@pytest.mark.parametrize("dealer_value", ALL_UPCARDS)
def test_ev5_hard11_double_is_argmax_all_upcards(dealer_value: str) -> None:
    """AC-B-EV5: hard 11 vs any upcard → 'double' is the argmax of action_evs."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("6"), _c("5")]  # hard 11
    evs = action_evs(hand, _c(dealer_value), can_double=True, can_split=False)
    best = max(evs, key=evs.__getitem__)
    assert best == "double", (
        f"hard 11 vs {dealer_value}: expected 'double' as argmax; got '{best}' "
        f"(evs={evs!r})"
    )


def test_ev5_soft18_vs_6_double_is_argmax() -> None:
    """AC-B-EV5: soft 18 [A,7] vs 6 → 'double' is the argmax of action_evs."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("A"), _c("7")]
    evs = action_evs(hand, _c("6"), can_double=True, can_split=False)
    best = max(evs, key=evs.__getitem__)
    assert best == "double", (
        f"soft 18 vs 6: expected 'double' as argmax; got '{best}' (evs={evs!r})"
    )


@pytest.mark.parametrize("dealer_value", ["9", "10", "A"])
def test_ev5_soft18_vs_9_10_A_hit_beats_stand(dealer_value: str) -> None:
    """AC-B-EV5: soft 18 [A,7] vs 9/10/A → ev(hit) > ev(stand)."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("A"), _c("7")]
    evs = action_evs(hand, _c(dealer_value), can_double=True, can_split=False)
    assert evs["hit"] > evs["stand"], (
        f"soft 18 vs {dealer_value}: hit EV {evs['hit']:.4f} should beat stand EV {evs['stand']:.4f}"
    )


def test_ev5_hard10_vs_9_double_is_argmax() -> None:
    """AC-B-EV5: hard 10 [6,4] vs 9 → 'double' is the argmax of action_evs."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("6"), _c("4")]  # hard 10
    evs = action_evs(hand, _c("9"), can_double=True, can_split=False)
    best = max(evs, key=evs.__getitem__)
    assert best == "double", (
        f"hard 10 vs 9: expected 'double' as argmax; got '{best}' (evs={evs!r})"
    )


# ─── AC-B-EV6: strategy cross-check sweep ────────────────────────────────────

# Allow-list of (hand_total, is_soft, upcard_value) cells where the infinite-deck
# model is expected to diverge from the 6-deck basic-strategy table in strategy.py.
# The implementer/tester may add up to 4 documented cells if the engine is provably
# correct but the infinite-deck vs 6-deck models legitimately disagree.
# Start EMPTY — do not pre-populate with guesses.
#
# Format: (player_total: int, is_soft: bool, upcard_value: str)
# Example (do not uncomment unless adding a real documented divergence):
#   (13, False, "2"),  # hard 13 vs 2: infinite-deck shifts one bucket
_STRATEGY_DIVERGENCE_ALLOW_LIST: set[tuple[int, bool, str]] = {
    # soft 13 (A+2) vs 5: infinite-deck EV argmax=hit (0.1336) > double (0.1272);
    # 6-deck basic strategy says double.  Tight margin (~0.006 bet), composition
    # effects in a 6-deck game tip the cell toward double (marginal soft-double boundary).
    (13, True, "5"),
    # soft 19 (A+8) vs 6: infinite-deck EV argmax=double (0.4611) > stand (0.4531);
    # 6-deck basic strategy says stand.  Dealer-6 bust probability is high enough in the
    # infinite-deck model to marginally favor doubling; 6-deck charts conservatively stand
    # (marginal soft-double boundary, infinite-deck vs 6-deck H17).
    (19, True, "6"),
}


def _strategy_cross_check_cases() -> list[tuple[int, bool, str]]:
    """Enumerate all (total, is_soft, upcard_value) sweep cells."""
    cases = []
    # Hard totals 5..20
    for total in range(5, 21):
        for upcard_value in ALL_UPCARDS:
            cases.append((total, False, upcard_value))
    # Soft totals 13..20
    for total in range(13, 21):
        for upcard_value in ALL_UPCARDS:
            cases.append((total, True, upcard_value))
    return cases


@pytest.mark.parametrize("total,is_soft,upcard_value", _strategy_cross_check_cases())
def test_ev6_strategy_cross_check(total: int, is_soft: bool, upcard_value: str) -> None:
    """AC-B-EV6: argmax of action_evs agrees with strategy.optimal_action for non-split decisions.

    The allow-list _STRATEGY_DIVERGENCE_ALLOW_LIST holds documented (total, is_soft, upcard)
    triples where infinite-deck and 6-deck basic strategy are known to disagree.
    Add entries there (with a comment) rather than weakening this assertion.
    """
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]
    from backend.game.blackjack.strategy import optimal_action

    # Build a representative 2-card hand so can_double=True
    if is_soft:
        hand = _soft_hand(total)
    else:
        hand = _hard_hand(total)

    upcard = _c(upcard_value)
    evs = action_evs(hand, upcard, can_double=True, can_split=False)
    ev_argmax = max(evs, key=evs.__getitem__)

    strat_action = optimal_action(hand, upcard, can_double=True, can_split=False)
    # strategy.optimal_action may return "split" for paired hands even when can_split=False
    # is not passed (we pass it explicitly), so it should never return split here.

    cell = (total, is_soft, upcard_value)
    if cell in _STRATEGY_DIVERGENCE_ALLOW_LIST:
        # Known documented divergence — skip assertion but do not silently pass
        pytest.xfail(
            reason=f"Documented infinite-deck vs 6-deck divergence at {cell}"
        )

    assert ev_argmax == strat_action, (
        f"{'soft' if is_soft else 'hard'} {total} vs {upcard_value}: "
        f"ev argmax='{ev_argmax}' but strategy.optimal_action='{strat_action}'. "
        f"If this is a genuine infinite-deck vs 6-deck divergence, add it to "
        f"_STRATEGY_DIVERGENCE_ALLOW_LIST with a comment."
    )


# ─── AC-B-EV7: ev_double ─────────────────────────────────────────────────────

@pytest.mark.parametrize("upcard_value", ALL_UPCARDS)
def test_ev7_hard11_double_beats_hit_and_stand(upcard_value: str) -> None:
    """AC-B-EV7: ev_double([5,6], upcard) > ev_hit([5,6], upcard) and > ev_stand(11,False,upcard)."""
    from backend.game.blackjack.ev import ev_double, ev_hit, ev_stand  # type: ignore[import]

    hand = [_c("5"), _c("6")]  # hard 11
    upcard = _c(upcard_value)
    d = ev_double(hand, upcard)
    h = ev_hit(hand, upcard)
    s = ev_stand(11, False, upcard)

    assert d > h, (
        f"hard 11 vs {upcard_value}: ev_double={d:.4f} should beat ev_hit={h:.4f}"
    )
    assert d > s, (
        f"hard 11 vs {upcard_value}: ev_double={d:.4f} should beat ev_stand={s:.4f}"
    )


def test_ev7_double_formula_matches_expected_stand_over_one_draw() -> None:
    """AC-B-EV7: ev_double is 2× the expected ev_stand (or -2 on bust) over one drawn rank.

    Verifies the formula: ev_double = sum_over_ranks(prob_rank * ev_after_draw)
    where ev_after_draw = 2*ev_stand(total+rank, ...) if not bust, else -2.
    We cross-check using hard 11 vs 6: compute expected value manually and
    compare to ev_double.
    """
    from backend.game.blackjack.ev import ev_double, ev_stand  # type: ignore[import]

    # Infinite-deck rank probabilities
    RANK_VALUES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]  # 11 = Ace
    RANK_PROBS = {r: (4 / 13 if r == 10 else 1 / 13) for r in RANK_VALUES}

    hand = [_c("5"), _c("6")]  # hard 11
    upcard = _c("6")
    player_base = 11  # hard total pre-draw

    expected_double = 0.0
    for rank, prob in RANK_PROBS.items():
        new_total = player_base + rank
        new_soft = (rank == 11)  # drawn Ace initially counts as 11 (soft=True)
        # Ace-demotion rule (mirrors ev._dealer_next_state / ev._advance):
        # if Ace drawn makes total > 21, count the Ace as 1 instead (hard).
        # Hard 11 + Ace: 11+11=22 → demote to 12, hard. No other rank busts from 11.
        if new_total > 21 and new_soft:
            new_total -= 10  # Ace counts as 1 → 12 (hard)
            new_soft = False
        if new_total > 21:
            expected_double += prob * (-2.0)
        else:
            expected_double += prob * 2.0 * ev_stand(new_total, new_soft, upcard)

    computed = ev_double(hand, upcard)
    assert computed == pytest.approx(expected_double, abs=1e-9), (
        f"ev_double([5,6], 6) = {computed:.6f}; manual formula gives {expected_double:.6f}"
    )


# ─── AC-B-EV8: ev_hit recursion ──────────────────────────────────────────────

@pytest.mark.parametrize("upcard_value", ALL_UPCARDS)
def test_ev8_hard5_hit_beats_stand_all_upcards(upcard_value: str) -> None:
    """AC-B-EV8: ev_hit of hard 5 > ev_stand(5,...) for every upcard (never stand on 5)."""
    from backend.game.blackjack.ev import ev_hit, ev_stand  # type: ignore[import]

    hand = [_c("3"), _c("2")]  # hard 5
    upcard = _c(upcard_value)
    h = ev_hit(hand, upcard)
    s = ev_stand(5, False, upcard)

    assert h > s, (
        f"ev_hit(hard 5) vs {upcard_value}: ev_hit={h:.4f} should beat ev_stand={s:.4f}"
    )


# ─── AC-B-EV9: determinism ───────────────────────────────────────────────────

def test_ev9_action_evs_is_deterministic() -> None:
    """AC-B-EV9: action_evs called twice with identical args returns identical dicts."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    hand = [_c("A"), _c("7")]
    upcard = _c("6")

    first = action_evs(hand, upcard, can_double=True, can_split=True)
    second = action_evs(hand, upcard, can_double=True, can_split=True)

    assert first == second, (
        f"action_evs is not deterministic: first call {first!r} != second call {second!r}"
    )


def test_ev9_determinism_multiple_calls_varied_hands() -> None:
    """AC-B-EV9: determinism holds across varied hand/upcard combinations."""
    from backend.game.blackjack.ev import action_evs  # type: ignore[import]

    test_cases = [
        ([_c("10"), _c("6")], _c("10"), False, False),   # hard 16 vs 10
        ([_c("6"), _c("5")], _c("7"), True, False),       # hard 11 vs 7
        ([_c("A"), _c("7")], _c("9"), True, False),       # soft 18 vs 9
        ([_c("8"), _c("8", "spades")], _c("A"), True, True),  # 8,8 vs A
    ]

    for hand, upcard, cd, cs in test_cases:
        r1 = action_evs(hand, upcard, can_double=cd, can_split=cs)
        r2 = action_evs(hand, upcard, can_double=cd, can_split=cs)
        assert r1 == r2, (
            f"action_evs not deterministic for hand={[c['value'] for c in hand]} "
            f"upcard={upcard['value']}: {r1!r} != {r2!r}"
        )
