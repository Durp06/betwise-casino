"""
test_game_engine.py — unit tests for backend.game.engine and resolve_hand
in backend.game.state.

Criteria source: specs/betwise-casino.md §T5, §T7, §7 test inventory.
Import path: backend.game.engine, backend.game.state
(ModuleNotFoundError until T5/T7 land)
"""

from __future__ import annotations

import pytest

from backend.game.engine import (
    can_double,
    can_split,
    card_rank,
    create_deck,
    deal_card,
    hand_value,
    is_blackjack,
    is_bust,
    is_soft,
)
from backend.game.state import resolve_hand


# ─── helpers ─────────────────────────────────────────────────────────────────

def card(value: str, suit: str = "spades") -> dict:
    return {"suit": suit, "value": value}


# ─── T5: deck creation ────────────────────────────────────────────────────────
# Criterion: create_deck() returns exactly 52 unique (suit, value) pairs.

def test_create_deck_returns_52_unique_cards():
    deck = create_deck()
    assert len(deck) == 52, f"Expected 52 cards, got {len(deck)}"
    pairs = {(c["suit"], c["value"]) for c in deck}
    assert len(pairs) == 52, "All 52 (suit, value) combinations must be unique"


# Criterion: deck is deterministic with an optional seed argument.

def test_create_deck_is_deterministic_with_seed():
    deck_a = create_deck(seed=42)
    deck_b = create_deck(seed=42)
    assert deck_a == deck_b, "Same seed must produce identical deck order"


# ─── T5: deal_card ────────────────────────────────────────────────────────────
# Criterion: deal_card pops the top card and returns (card, shorter deck);
# must NOT mutate the input list.

def test_deal_card_removes_from_deck():
    deck = create_deck(seed=0)
    original_len = len(deck)
    # Make a shallow copy to detect mutation
    deck_before = list(deck)
    popped, remaining = deal_card(deck)
    # Input must be unchanged (deal_card must return a new list)
    assert deck == deck_before, "deal_card must not mutate the input list"
    assert len(remaining) == original_len - 1
    assert popped not in remaining, "Dealt card must not appear in remaining deck"


# ─── T5: hand_value — ace demotion logic ─────────────────────────────────────
# Criterion: ace counts as 11 when it doesn't cause a bust.

def test_hand_value_counts_ace_as_11_when_safe():
    cards = [card("A"), card("6")]  # 11+6 = 17, safe
    assert hand_value(cards) == 17


# Criterion: [A, 5, 7] → 13 (demote ace: 1+5+7=13, not 23)

def test_hand_value_counts_ace_as_1_to_avoid_bust():
    cards = [card("A"), card("5"), card("7")]  # 11+5+7=23 → demote → 1+5+7=13
    assert hand_value(cards) == 13


# Criterion: [A, A] → 12  (one ace as 11, one as 1)

def test_hand_value_two_aces_equals_12():
    cards = [card("A"), card("A")]  # 11+11=22 → demote one → 11+1=12
    assert hand_value(cards) == 12


# Additional parametrized cases from plan §7:

@pytest.mark.parametrize("hand,expected", [
    ([card("A"), card("6"), card("10")], 17),   # 11+6+10=27 → demote → 1+6+10=17
    ([card("A"), card("A")],             12),   # two aces → 12
    ([card("A"), card("A"), card("9")],  21),   # 11+1+9=21
    ([card("A"), card("A"), card("A"), card("9")], 12),  # 11+1+1+9=22→1+1+1+9=12
])
def test_hand_value_ace_demotion_parametrized(hand, expected):
    assert hand_value(hand) == expected, (
        f"hand_value({[c['value'] for c in hand]}) should be {expected}"
    )


# ─── T5: is_soft ─────────────────────────────────────────────────────────────
# Criterion: is_soft returns True when an ace is being counted as 11.

def test_is_soft_true_for_promoted_ace():
    assert is_soft([card("A"), card("7")]) is True   # soft 18 — ace still 11


def test_is_soft_false_after_ace_demotion():
    # A+5+7 = 13 with ace demoted → not soft
    assert is_soft([card("A"), card("5"), card("7")]) is False


# ─── T5: is_blackjack ────────────────────────────────────────────────────────
# Criterion: is_blackjack True only for exactly 2 cards totaling 21.

def test_is_blackjack_true_for_ace_plus_ten():
    assert is_blackjack([card("A"), card("K")]) is True


def test_is_blackjack_false_for_three_card_21():
    # Three-card 21 is NOT a blackjack
    assert is_blackjack([card("A"), card("5"), card("5")]) is False


def test_is_blackjack_only_for_two_cards_totaling_21():
    assert is_blackjack([card("A"), card("10")]) is True
    assert is_blackjack([card("K"), card("A")]) is True
    assert is_blackjack([card("7"), card("7"), card("7")]) is False  # 21 but 3 cards
    assert is_blackjack([card("9"), card("7")]) is False  # 2 cards but not 21


# ─── T5: is_bust ─────────────────────────────────────────────────────────────
# Criterion: is_bust True when hand value > 21.

def test_is_bust_above_21():
    assert is_bust([card("10"), card("7"), card("6")]) is True   # 23
    assert is_bust([card("10"), card("7")]) is False             # 17
    assert is_bust([card("10"), card("7"), card("4")]) is False  # 21 — exactly 21, not bust


# ─── T5: can_split ───────────────────────────────────────────────────────────
# Criterion: can_split True for exactly 2 cards of same value;
# face cards collapse to 10 so K-Q is a splittable pair-of-10s.

def test_can_split_same_value_pair():
    assert can_split([card("8"), card("8")]) is True
    assert can_split([card("A"), card("A")]) is True
    assert can_split([card("8"), card("9")]) is False


def test_can_split_face_cards_collapse_to_10():
    # K and Q both rank as 10 → splittable
    assert can_split([card("K"), card("Q")]) is True
    assert can_split([card("J"), card("10")]) is True
    assert can_split([card("K"), card("K")]) is True


def test_can_split_requires_exactly_two_cards():
    assert can_split([card("8")]) is False
    assert can_split([card("8"), card("8"), card("8")]) is False


# ─── T5: can_double ──────────────────────────────────────────────────────────
# Criterion: can_double True only when exactly 2 cards in hand.

def test_can_double_only_with_two_cards():
    assert can_double([card("5"), card("6")]) is True
    assert can_double([card("5"), card("6"), card("2")]) is False
    assert can_double([card("5")]) is False


# ─── T7: resolve_hand ────────────────────────────────────────────────────────
# Criterion: blackjack payout = bet * 5 // 2  (3:2, integer math)

def test_resolve_hand_blackjack_payout_is_bet_times_5_div_2():
    # Hand: blackjack (A + K); dealer does not have blackjack (non-21 hand)
    hand_cards = [card("A"), card("K")]
    dealer_cards = [card("10"), card("7")]  # dealer 17
    bet = 1_000
    outcome, payout = resolve_hand(
        hand={"cards": hand_cards, "bet": bet, "status": "blackjack"},
        dealer_cards=dealer_cards,
    )
    assert outcome == "blackjack"
    assert payout == bet * 5 // 2, f"Blackjack payout should be {bet * 5 // 2}, got {payout}"


# Criterion: push → return original bet

def test_resolve_hand_push_returns_bet():
    # Player 20, dealer 20 → push
    hand_cards = [card("K"), card("10")]
    dealer_cards = [card("Q"), card("10")]
    bet = 2_000
    outcome, payout = resolve_hand(
        hand={"cards": hand_cards, "bet": bet, "status": "active"},
        dealer_cards=dealer_cards,
    )
    assert outcome == "push"
    assert payout == bet


# Criterion: bust → payout 0

def test_resolve_hand_bust_pays_zero():
    bust_cards = [card("10"), card("7"), card("6")]  # 23 — bust
    dealer_cards = [card("10"), card("7")]
    bet = 1_500
    outcome, payout = resolve_hand(
        hand={"cards": bust_cards, "bet": bet, "status": "bust"},
        dealer_cards=dealer_cards,
    )
    assert outcome == "bust"
    assert payout == 0


# Parametrized for all 5 outcome buckets:
# blackjack, win, push, loss, bust

@pytest.mark.parametrize("player_hand_value,dealer_hand_value,player_status,expected_outcome,bet_multiplier", [
    # player wins outright
    (20, 18, "active",    "win",       2),    # player 20 > dealer 18 → win, bet*2
    # push
    (19, 19, "active",    "push",      1),    # tie → push, original bet back
    # player loses
    (17, 20, "active",    "loss",      0),    # player 17 < dealer 20 → loss
    # dealer busts, player does not
    (18, 22, "active",    "win",       2),    # dealer bust → player wins
])
def test_resolve_hand_all_outcome_buckets(player_hand_value, dealer_hand_value, player_status, expected_outcome, bet_multiplier):
    # Build minimal synthetic hands. 2 cards for totals ≤ 20; 3 cards for bust
    # totals (22+ can't be reached with two non-Ace cards).
    def hand_cards_for(total):
        """Return a hand summing to `total`. Uses 3 cards for bust totals."""
        if total <= 11:
            return [card("2"), card(str(total - 2))]
        if total <= 20:
            rem = total - 10
            return [card("10"), card(str(rem))]
        if total == 21:
            # Non-blackjack 21 (3 cards so is_blackjack returns False).
            return [card("7"), card("7"), card("7")]
        # Bust: 3-card hand summing to `total`. e.g. 22 = 10 + 8 + 4.
        return [card("10"), card("8"), card(str(total - 18))]

    p_cards = hand_cards_for(player_hand_value)
    d_cards = hand_cards_for(dealer_hand_value)
    bet = 1_000
    outcome, payout = resolve_hand(
        hand={"cards": p_cards, "bet": bet, "status": player_status},
        dealer_cards=d_cards,
    )
    assert outcome == expected_outcome, f"Expected {expected_outcome}, got {outcome}"
    assert payout == bet * bet_multiplier, f"Expected payout {bet * bet_multiplier}, got {payout}"
