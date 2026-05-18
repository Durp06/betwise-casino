"""
test_strategy.py — unit tests for the bronze-piece basic-strategy engine.

Every test maps 1-to-1 to a criterion in specs/betwise-casino.md §T6 / §7
and the verbatim test names listed in specs/betwise-casino-source.md Step 6.

Import path: backend.game.strategy  (ModuleNotFoundError until T6 lands)
"""

from __future__ import annotations

import pytest

from backend.game.strategy import explain_decision, optimal_action

# ─── helpers ─────────────────────────────────────────────────────────────────

def card(value: str, suit: str = "spades") -> dict:
    return {"suit": suit, "value": value}


# All 10 dealer upcards (2-10 + A) represented as card dicts
ALL_DEALER_UPCARDS = [card(v) for v in ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]]


# ─── Hard totals ──────────────────────────────────────────────────────────────
# Criterion: hard_16 vs dealer 10 → hit  (T6 row 13-16, upcard 7-A → hit)

def test_hard_16_vs_dealer_10_should_hit():
    player = [card("9"), card("7")]  # hard 16
    dealer = card("10")
    assert optimal_action(player, dealer) == "hit"


# Criterion: hard_17 vs dealer Ace → stand  (T6 row 17+ → always stand)

def test_hard_17_vs_dealer_ace_should_stand():
    player = [card("10"), card("7")]  # hard 17
    dealer = card("A")
    assert optimal_action(player, dealer) == "stand"


# Criterion: hard_11 vs dealer 6 → double  (T6 row 11, upcard 2-10 → double)

def test_hard_11_vs_dealer_6_should_double():
    player = [card("5"), card("6")]  # hard 11
    dealer = card("6")
    assert optimal_action(player, dealer) == "double"


# Criterion: hard_11 vs dealer Ace → double  (6-deck H17 chart: all upcards → double)

def test_hard_11_vs_dealer_ace_should_double():
    player = [card("5"), card("6")]  # hard 11
    dealer = card("A")
    assert optimal_action(player, dealer) == "double", (
        "Hard 11 vs dealer Ace should double on 6-deck H17 chart"
    )


# Criterion: hard_12 vs dealer 4 → stand  (T6 row 12, upcard 4-6 → stand)

def test_hard_12_vs_dealer_4_should_stand():
    player = [card("7"), card("5")]  # hard 12
    dealer = card("4")
    assert optimal_action(player, dealer) == "stand"


# Criterion: hard_8 vs any dealer upcard → always hit  (T6 row 8-)
# Parametrized over all 10 upcards so every path is covered.

@pytest.mark.parametrize("dealer_card", ALL_DEALER_UPCARDS)
def test_hard_8_vs_dealer_anything_should_hit(dealer_card):
    player = [card("5"), card("3")]  # hard 8
    assert optimal_action(player, dealer_card) == "hit"


# ─── Soft totals ──────────────────────────────────────────────────────────────
# Criterion: soft_17 (A+6) vs dealer 3 → double  (T6 soft-17 row, 3-6 → double)

def test_soft_17_vs_dealer_3_should_double():
    player = [card("A"), card("6")]  # soft 17
    dealer = card("3")
    assert optimal_action(player, dealer) == "double"


# Criterion: soft_18 (A+7) vs dealer 9 → hit  (T6 soft-18 row, 9/10/A → hit)

def test_soft_18_vs_dealer_9_should_hit():
    player = [card("A"), card("7")]  # soft 18
    dealer = card("9")
    assert optimal_action(player, dealer) == "hit"


# Criterion: soft_18 (A+7) vs dealer 7 → stand  (T6 soft-18 row, 2/7/8 → stand)

def test_soft_18_vs_dealer_7_should_stand():
    player = [card("A"), card("7")]  # soft 18
    dealer = card("7")
    assert optimal_action(player, dealer) == "stand"


# ─── Pairs ────────────────────────────────────────────────────────────────────
# Criterion: A-A always split

def test_pair_aces_always_split():
    player = [card("A"), card("A")]
    for dealer in ALL_DEALER_UPCARDS:
        assert optimal_action(player, dealer) == "split", (
            f"Expected split for pair of aces vs dealer {dealer['value']}"
        )


# Criterion: 10-10 (and J/Q/K pairs and mixed face) never split — always stand
# Parametrize over all "pair of tens" combinations.

@pytest.mark.parametrize("v1,v2", [
    ("10", "10"),
    ("J",  "J"),
    ("Q",  "Q"),
    ("K",  "K"),
    ("10", "K"),  # mixed face cards — still a pair-of-10s
])
def test_pair_tens_never_split(v1, v2):
    player = [card(v1), card(v2)]
    dealer = card("6")  # most aggressive split upcard — still must stand
    result = optimal_action(player, dealer)
    assert result == "stand", (
        f"Expected stand for {v1}-{v2} pair vs dealer 6, got {result!r}"
    )


# Criterion: 8-8 always split

def test_pair_eights_always_split():
    player = [card("8"), card("8")]
    for dealer in ALL_DEALER_UPCARDS:
        assert optimal_action(player, dealer) == "split", (
            f"Expected split for pair of 8s vs dealer {dealer['value']}"
        )


# Criterion: 5-5 treated as hard 10, NEVER split

def test_pair_fives_treat_as_hard_10():
    # Hard 10 vs dealer 6 → double (not split, not hit)
    player = [card("5"), card("5")]
    dealer = card("6")
    result = optimal_action(player, dealer)
    assert result in ("double", "hit"), (
        f"5-5 should be treated as hard 10, never split; got {result!r}"
    )
    assert result != "split", "5-5 must never be split per spec"
    # Also verify the standard hard-10-vs-6 action is double
    assert result == "double", "Hard 10 vs dealer 6 should double"


# ─── Edge cases ───────────────────────────────────────────────────────────────
# Criterion: when can_double=False and strategy says double → return hit
# (post-hit situation — only 2 original cards legally double)

def test_cannot_double_after_hit_falls_back_to_hit():
    player = [card("5"), card("6")]  # hard 11 → normally doubles vs 6
    dealer = card("6")
    # Confirm the normal recommendation is double
    assert optimal_action(player, dealer, can_double=True) == "double"
    # With can_double=False it must fall back to hit, not stand
    result = optimal_action(player, dealer, can_double=False)
    assert result == "hit", (
        f"Expected hit when can_double=False for hard 11 vs 6, got {result!r}"
    )


# Criterion: when can_split=False and strategy says split → evaluate as hard total

def test_cannot_split_evaluates_as_hard_total():
    # A-A with can_split=False: the hard total is 12 (or 2 if you demote both;
    # but strategy code must treat as hard 12 vs e.g. dealer 10 → hit)
    player = [card("A"), card("A")]
    dealer = card("10")
    # Normal action is split
    assert optimal_action(player, dealer, can_split=True) == "split"
    # When can_split=False the pair is evaluated as a hard total → must NOT be split
    result = optimal_action(player, dealer, can_split=False)
    assert result != "split", (
        f"When can_split=False, result must not be 'split'; got {result!r}"
    )
    # Hard 12 vs dealer 10 → hit (spec: stand vs 4-6, hit otherwise)
    assert result == "hit"


# ─── explain_decision ─────────────────────────────────────────────────────────
# Criterion: explain_decision returns a non-empty string containing the hand
# category and the dealer upcard value (e.g. "soft 17 vs dealer 6").

def test_explain_decision_returns_nonempty_string():
    player = [card("A"), card("6")]  # soft 17
    dealer = card("6")
    text = explain_decision(
        player_cards=player,
        dealer_upcard=dealer,
        was_correct=True,
        player_guess="double",
        optimal="double",
    )
    assert isinstance(text, str) and len(text) > 0, "explain_decision must return a non-empty string"


def test_explain_decision_includes_hand_category_and_dealer_upcard():
    player = [card("A"), card("6")]  # soft 17
    dealer = card("6")
    text = explain_decision(
        player_cards=player,
        dealer_upcard=dealer,
        was_correct=True,
        player_guess="double",
        optimal="double",
    )
    lower = text.lower()
    # Must mention the hand type and the dealer upcard somewhere
    assert "soft" in lower or "17" in lower, (
        f"explain_decision should mention 'soft' or '17': {text!r}"
    )
    assert "6" in text, (
        f"explain_decision should mention dealer upcard '6': {text!r}"
    )


# ─── 9-9 pair — full parametrized coverage ───────────────────────────────────
# Criterion: 9-9 → split vs dealer 2-6 and 8-9; stand vs dealer 7, 10, A

@pytest.mark.parametrize("dealer_value,expected", [
    ("2",  "split"),
    ("3",  "split"),
    ("4",  "split"),
    ("5",  "split"),
    ("6",  "split"),
    ("7",  "stand"),
    ("8",  "split"),
    ("9",  "split"),
    ("10", "stand"),
    ("A",  "stand"),
])
def test_pair_nines_split_vs_2_through_6_and_8_9_stand_vs_7_10_A(dealer_value, expected):
    player = [card("9"), card("9")]
    dealer = card(dealer_value)
    result = optimal_action(player, dealer)
    assert result == expected, (
        f"9-9 vs dealer {dealer_value}: expected {expected!r}, got {result!r}"
    )
