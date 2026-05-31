"""
test_strategy_soft18.py — Regression tests for soft-18 no-double fallback fix.

Acceptance criteria: AC-B-STRAT1 through AC-B-STRAT5 (specs/blackjack-study.md).

The bug (AC-B-STRAT1): optimal_action([A,7], dealer, can_double=False) returns
"hit" for dealer upcards 2-6.  The correct fallback is "stand" because the
soft-18 table already says stand vs 7/8, and the double vs 2-6 cells have
"stand" as the correct no-double downgrade (not hit).
"""

from __future__ import annotations

import pytest

from backend.game.blackjack.strategy import optimal_action


# ─── card helper ─────────────────────────────────────────────────────────────

def _c(value: str, suit: str = "hearts") -> dict:
    return {"suit": suit, "value": value}


# ─── AC-B-STRAT1 ─────────────────────────────────────────────────────────────
# [A,7] (soft 18) vs dealer 2..6 with can_double=False must return "stand".
# This is the failing case: current code downgrades double -> hit instead of stand.

@pytest.mark.parametrize("dealer_value", ["2", "3", "4", "5", "6"])
def test_soft18_no_double_vs_weak_upcard_returns_stand(dealer_value: str) -> None:
    """AC-B-STRAT1: soft 18 + can_double=False vs {2,3,4,5,6} → stand, not hit."""
    hand = [_c("A"), _c("7")]
    dealer = _c(dealer_value)
    action = optimal_action(hand, dealer, can_double=False)
    assert action == "stand", (
        f"soft 18 vs dealer {dealer_value} with can_double=False should be 'stand'; "
        f"got '{action}' — the no-double fallback for soft 18 must return stand."
    )


# ─── AC-B-STRAT2 ─────────────────────────────────────────────────────────────
# [A,7] (soft 18) vs dealer 9, 10, A with can_double=False must return "hit".

@pytest.mark.parametrize("dealer_value", ["9", "10", "A"])
def test_soft18_no_double_vs_strong_upcard_returns_hit(dealer_value: str) -> None:
    """AC-B-STRAT2: soft 18 + can_double=False vs {9,10,A} → hit."""
    hand = [_c("A"), _c("7")]
    dealer = _c(dealer_value)
    action = optimal_action(hand, dealer, can_double=False)
    assert action == "hit", (
        f"soft 18 vs dealer {dealer_value} with can_double=False should be 'hit'; "
        f"got '{action}'."
    )


# ─── AC-B-STRAT3 ─────────────────────────────────────────────────────────────
# [A,7] (soft 18) vs dealer 7/8 must return "stand" regardless of can_double.
# The SOFT_TOTALS table already has stand for these cells (not double), so the
# downgrade block is never hit — confirming the fix does not regress these.

@pytest.mark.parametrize("dealer_value", ["7", "8"])
@pytest.mark.parametrize("cd", [True, False])
def test_soft18_vs_7_or_8_always_stands(dealer_value: str, cd: bool) -> None:
    """AC-B-STRAT3: soft 18 vs {7,8} is stand regardless of can_double."""
    hand = [_c("A"), _c("7")]
    dealer = _c(dealer_value)
    action = optimal_action(hand, dealer, can_double=cd)
    assert action == "stand", (
        f"soft 18 vs dealer {dealer_value} (can_double={cd}) should be 'stand'; "
        f"got '{action}'."
    )


# ─── AC-B-STRAT4 ─────────────────────────────────────────────────────────────
# Soft 17 ([A,6]) with can_double=False vs 3..6 must downgrade to "hit"
# (there is no stand fallback for soft 17 — the table says double vs 3-6).
# This verifies the fix does NOT accidentally change soft-17 behaviour.

@pytest.mark.parametrize("dealer_value", ["3", "4", "5", "6"])
def test_soft17_no_double_vs_weak_upcard_returns_hit(dealer_value: str) -> None:
    """AC-B-STRAT4: soft 17 + can_double=False vs {3,4,5,6} → hit (unaffected by fix)."""
    hand = [_c("A"), _c("6")]
    dealer = _c(dealer_value)
    action = optimal_action(hand, dealer, can_double=False)
    assert action == "hit", (
        f"soft 17 vs dealer {dealer_value} with can_double=False should be 'hit'; "
        f"got '{action}'."
    )


# ─── AC-B-STRAT5 ─────────────────────────────────────────────────────────────
# Soft 19+ ([A,8] soft 19, [A,9] soft 20) with can_double=False must return "stand".
# These are regression guards — SOFT_TOTALS already shows stand for all upcards.
# The fix must not break them when can_double=False causes the downgrade block to
# be checked.

@pytest.mark.parametrize("pair", [("A", "8"), ("A", "9")])
@pytest.mark.parametrize("dealer_value", ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"])
def test_soft19_plus_no_double_returns_stand(pair: tuple[str, str], dealer_value: str) -> None:
    """AC-B-STRAT5: soft 19/20 + can_double=False → stand for every upcard."""
    hand = [_c(pair[0]), _c(pair[1])]
    dealer = _c(dealer_value)
    action = optimal_action(hand, dealer, can_double=False)
    assert action == "stand", (
        f"soft {19 if pair[1]=='8' else 20} vs dealer {dealer_value} "
        f"with can_double=False should be 'stand'; got '{action}'."
    )
