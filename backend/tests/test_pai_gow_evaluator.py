"""
test_pai_gow_evaluator.py — unit tests for backend/game/pai_gow/evaluator.py.

Covers (spec §7.2, §7.3, §7.4, §11.1):
- All 9 hand categories (high card → straight flush) for 5-card hands.
- 2-card hand scoring (pair > high card only).
- Joker semi-wild semantics: completes straight/flush/straight-flush; else Ace.
- A-K-Q-J-10 is the HIGHEST straight (rank 10).
- A-2-3-4-5 is the SECOND-HIGHEST straight (rank 9) — US Pai Gow rule.
- Unified 2-card-vs-5-card comparison protocol.
- Kicker tiebreaks.
- best_five_card_hand from 7 cards.
- 7-card straight flush detection (Fortune GRAND tier).
"""
from __future__ import annotations

import pytest

from backend.game.pai_gow.cards import JOKER
from backend.game.pai_gow.evaluator import (
    FLUSH,
    FOUR_OF_A_KIND,
    FULL_HOUSE,
    HIGH_CARD,
    ONE_PAIR,
    STRAIGHT,
    STRAIGHT_FLUSH,
    THREE_OF_A_KIND,
    TWO_PAIR,
    best_five_card_hand,
    compare_hands,
    is_seven_card_straight_flush,
    score_hand,
)


_SUIT_SHORT_TO_FULL = {"h": "hearts", "d": "diamonds", "c": "clubs", "s": "spades"}


def C(suit: str, value: str) -> dict:
    """Convenience card constructor. Accepts short ('h') or full ('hearts') suits."""
    return {"suit": _SUIT_SHORT_TO_FULL.get(suit, suit), "value": value}


# ─── 5-card hand category detection ──────────────────────────────────────────


def test_high_card_5():
    hand = [C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    s = score_hand(hand)
    assert s[0] == HIGH_CARD
    assert s == (HIGH_CARD, 14, 13, 12, 9, 5)


def test_one_pair_5():
    hand = [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    assert score_hand(hand) == (ONE_PAIR, 13, 12, 9, 5)


def test_two_pair_5():
    hand = [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "Q"), C("h", "5")]
    assert score_hand(hand) == (TWO_PAIR, 13, 12, 5)


def test_three_of_a_kind_5():
    hand = [C("h", "9"), C("s", "9"), C("d", "9"), C("c", "K"), C("h", "5")]
    assert score_hand(hand) == (THREE_OF_A_KIND, 9, 13, 5)


def test_straight_5_king_high():
    """K-Q-J-10-9 → straight rank 8."""
    hand = [C("h", "K"), C("s", "Q"), C("d", "J"), C("c", "10"), C("h", "9")]
    assert score_hand(hand) == (STRAIGHT, 8)


def test_straight_5_ace_high_broadway():
    """A-K-Q-J-10 is the HIGHEST straight (rank 10)."""
    hand = [C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "J"), C("h", "10")]
    assert score_hand(hand) == (STRAIGHT, 10)


def test_straight_5_wheel_second_highest():
    """A-2-3-4-5 is the SECOND-HIGHEST straight (rank 9) — US Pai Gow §7.2."""
    hand = [C("h", "A"), C("s", "2"), C("d", "3"), C("c", "4"), C("h", "5")]
    assert score_hand(hand) == (STRAIGHT, 9)


def test_broadway_beats_wheel():
    broadway = [C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "J"), C("h", "10")]
    wheel = [C("h", "A"), C("s", "2"), C("d", "3"), C("c", "4"), C("h", "5")]
    assert score_hand(broadway) > score_hand(wheel)


def test_wheel_beats_king_high_straight():
    """Wheel (rank 9) > K-high straight (rank 8) — the round-4 §7.2 pin."""
    wheel = [C("h", "A"), C("s", "2"), C("d", "3"), C("c", "4"), C("h", "5")]
    king_high = [C("h", "K"), C("s", "Q"), C("d", "J"), C("c", "10"), C("h", "9")]
    assert score_hand(wheel) > score_hand(king_high)


def test_flush_5():
    hand = [C("h", "K"), C("h", "Q"), C("h", "9"), C("h", "5"), C("h", "2")]
    assert score_hand(hand) == (FLUSH, 13, 12, 9, 5, 2)


def test_full_house_5():
    hand = [C("h", "9"), C("s", "9"), C("d", "9"), C("c", "K"), C("h", "K")]
    assert score_hand(hand) == (FULL_HOUSE, 9, 13)


def test_four_of_a_kind_5():
    hand = [C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"), C("h", "5")]
    assert score_hand(hand) == (FOUR_OF_A_KIND, 13, 5)


def test_straight_flush_5():
    """9-8-7-6-5 of hearts → 9-high SF. Straight rank: 9-5=4 (per §7.2 encoding)."""
    hand = [C("h", "9"), C("h", "8"), C("h", "7"), C("h", "6"), C("h", "5")]
    assert score_hand(hand) == (STRAIGHT_FLUSH, 4)


def test_royal_flush_5_is_highest_straight_flush():
    royal = [C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "10")]
    assert score_hand(royal) == (STRAIGHT_FLUSH, 10)


def test_straight_flush_wheel_is_second_highest_sf():
    """Wheel SF is second-highest SF, parallel to wheel-straight being 2nd."""
    wheel_sf = [C("h", "A"), C("h", "2"), C("h", "3"), C("h", "4"), C("h", "5")]
    assert score_hand(wheel_sf) == (STRAIGHT_FLUSH, 9)


# ─── Category ordering (each category > all below) ───────────────────────────


def test_category_ordering_lowest_to_highest():
    hands = [
        ("high card", [C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]),
        ("one pair", [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]),
        ("two pair", [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "Q"), C("h", "5")]),
        ("three of a kind", [C("h", "9"), C("s", "9"), C("d", "9"), C("c", "K"), C("h", "5")]),
        ("straight", [C("h", "9"), C("s", "8"), C("d", "7"), C("c", "6"), C("h", "5")]),
        ("flush", [C("h", "K"), C("h", "J"), C("h", "9"), C("h", "5"), C("h", "2")]),
        ("full house", [C("h", "9"), C("s", "9"), C("d", "9"), C("c", "K"), C("h", "K")]),
        ("four of a kind", [C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"), C("h", "5")]),
        ("straight flush", [C("h", "9"), C("h", "8"), C("h", "7"), C("h", "6"), C("h", "5")]),
    ]
    scores = [score_hand(h) for _, h in hands]
    for i in range(len(scores) - 1):
        assert scores[i] < scores[i + 1], (
            f"{hands[i][0]} should be lower than {hands[i+1][0]}: "
            f"{scores[i]} vs {scores[i+1]}"
        )


# ─── Kicker tiebreaks ────────────────────────────────────────────────────────


def test_kicker_breaks_pair_tie():
    p1 = [C("h", "K"), C("s", "K"), C("d", "A"), C("c", "9"), C("h", "5")]
    p2 = [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    assert score_hand(p1) > score_hand(p2)


def test_higher_pair_beats_lower_pair_regardless_of_kickers():
    p1 = [C("h", "K"), C("s", "K"), C("d", "2"), C("c", "3"), C("h", "4")]
    p2 = [C("h", "Q"), C("s", "Q"), C("d", "A"), C("c", "K"), C("h", "J")]
    assert score_hand(p1) > score_hand(p2)


# ─── 2-card hands ────────────────────────────────────────────────────────────


def test_two_card_high_card():
    assert score_hand([C("h", "A"), C("s", "K")]) == (HIGH_CARD, 14, 13)


def test_two_card_pair():
    assert score_hand([C("h", "K"), C("s", "K")]) == (ONE_PAIR, 13)


def test_two_card_pair_beats_any_two_card_high_card():
    pair = [C("h", "2"), C("s", "2")]
    high = [C("h", "A"), C("s", "K")]
    assert score_hand(pair) > score_hand(high)


# ─── Unified 2-card vs 5-card comparison (§7.3 — load-bearing for foul rule) ─


def test_5card_pair_with_kickers_beats_2card_same_pair():
    """5-card pair-of-Ks with kickers beats 2-card pair-of-Ks alone.
    Round-6 #13 — what makes high-quad split (KK|KK+kickers) legal, not foul.
    """
    five = [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    two = [C("h", "K"), C("s", "K")]
    assert score_hand(five) > score_hand(two)


def test_2card_pair_beats_5card_high_card():
    """Even a low 2-card pair beats a 5-card high-card (category dominance)."""
    pair = [C("h", "2"), C("s", "2")]
    high5 = [C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    assert score_hand(pair) > score_hand(high5)


# ─── Joker semi-wild semantics (§7.1) ────────────────────────────────────────


def test_joker_in_5card_falls_back_to_ace_when_no_completion_possible():
    """K-Q-J-7 + joker: gap is too wide to complete a straight; no 4 same suit
    so no flush. Joker = Ace (default). Result: A-K-Q-J-7 high card.
    """
    hand = [JOKER, C("s", "K"), C("d", "Q"), C("c", "J"), C("h", "7")]
    assert score_hand(hand) == (HIGH_CARD, 14, 13, 12, 11, 7)


def test_joker_completes_inside_straight():
    """K-Q-J-9 + joker → joker as 10 gives K-Q-J-10-9 straight (rank 8)."""
    hand = [JOKER, C("s", "K"), C("d", "Q"), C("c", "J"), C("h", "9")]
    assert score_hand(hand) == (STRAIGHT, 8)


def test_joker_completes_top_straight_via_ace():
    """K-Q-J-10 + joker → joker as Ace gives A-K-Q-J-10 broadway (rank 10)."""
    hand = [JOKER, C("s", "K"), C("d", "Q"), C("c", "J"), C("h", "10")]
    assert score_hand(hand) == (STRAIGHT, 10)


def test_joker_completes_wheel_straight():
    """2-3-4-5 + joker → joker as Ace gives A-2-3-4-5 wheel (rank 9)."""
    hand = [JOKER, C("h", "2"), C("s", "3"), C("d", "4"), C("c", "5")]
    assert score_hand(hand) == (STRAIGHT, 9)


def test_joker_completes_flush():
    """4 hearts + joker → joker as Ace of hearts gives flush."""
    hand = [JOKER, C("hearts", "K"), C("hearts", "J"), C("hearts", "9"), C("hearts", "5")]
    assert score_hand(hand) == (FLUSH, 14, 13, 11, 9, 5)


def test_joker_completes_royal_flush():
    """K-Q-J-10 of hearts + joker → royal flush."""
    hand = [JOKER, C("hearts", "K"), C("hearts", "Q"), C("hearts", "J"), C("hearts", "10")]
    assert score_hand(hand) == (STRAIGHT_FLUSH, 10)


def test_joker_cannot_pair_non_ace_rank():
    """K-K-Q-J + joker should NOT become trips of K. Semi-wild rule: joker is
    only Ace OR completes straight/flush/SF — never duplicates a non-Ace rank.
    """
    hand = [JOKER, C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "J")]
    # Joker as Ace → A-K-K-Q-J: pair of K with A,Q,J kickers
    assert score_hand(hand) == (ONE_PAIR, 13, 14, 12, 11)


def test_joker_pairs_with_existing_ace_in_5card():
    """A-K-Q-J + joker → pair of aces (joker is Ace by default)."""
    hand = [JOKER, C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "J")]
    # Joker as Ace gives A-A-K-Q-J = pair of A's with K,Q,J kickers
    # But also: joker as 10 gives A-K-Q-J-10 broadway straight rank 10
    # Straight > one pair → MAX is the straight
    assert score_hand(hand) == (STRAIGHT, 10)


def test_joker_two_card_is_ace_high_with_non_ace():
    """Joker + K (2-card) → joker is Ace, hand is A-K high."""
    assert score_hand([JOKER, C("h", "K")]) == (HIGH_CARD, 14, 13)


def test_joker_two_card_pair_with_existing_ace():
    """Joker + A (2-card) → pair of aces."""
    assert score_hand([JOKER, C("h", "A")]) == (ONE_PAIR, 14)


# ─── best_five_card_hand from 7 cards ────────────────────────────────────────


def test_best_five_picks_full_house_over_three_of_a_kind():
    """Three 9s + pair of Ks + 2 random → best 5 = full house."""
    seven = [
        C("h", "9"), C("s", "9"), C("d", "9"),
        C("c", "K"), C("h", "K"),
        C("d", "5"), C("c", "2"),
    ]
    best, score = best_five_card_hand(seven)
    assert score == (FULL_HOUSE, 9, 13)
    assert len(best) == 5


def test_best_five_picks_flush_when_5_suited_present():
    seven = [
        C("h", "K"), C("h", "Q"), C("h", "9"), C("h", "5"), C("h", "2"),
        C("s", "3"), C("c", "7"),
    ]
    _, score = best_five_card_hand(seven)
    assert score[0] == FLUSH


def test_best_five_picks_straight_when_5_consecutive_present():
    seven = [
        C("h", "9"), C("s", "8"), C("d", "7"), C("c", "6"), C("h", "5"),
        C("s", "K"), C("c", "2"),
    ]
    _, score = best_five_card_hand(seven)
    assert score[0] == STRAIGHT


def test_best_five_returns_exactly_5_cards():
    seven = [
        C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "J"), C("h", "10"),
        C("s", "5"), C("c", "2"),
    ]
    best, _ = best_five_card_hand(seven)
    assert len(best) == 5


# ─── 7-card straight flush (Fortune GRAND tier) ──────────────────────────────


def test_seven_card_straight_flush_true_basic():
    seven = [
        C("h", "2"), C("h", "3"), C("h", "4"), C("h", "5"),
        C("h", "6"), C("h", "7"), C("h", "8"),
    ]
    assert is_seven_card_straight_flush(seven) is True


def test_seven_card_straight_flush_true_ace_high():
    seven = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"),
        C("h", "10"), C("h", "9"), C("h", "8"),
    ]
    assert is_seven_card_straight_flush(seven) is True


def test_seven_card_straight_flush_true_wheel_extended():
    """A-2-3-4-5-6-7 of one suit (Ace treated as 1) is a 7-card SF."""
    seven = [
        C("s", "A"), C("s", "2"), C("s", "3"), C("s", "4"),
        C("s", "5"), C("s", "6"), C("s", "7"),
    ]
    assert is_seven_card_straight_flush(seven) is True


def test_seven_card_straight_flush_false_mixed_suits():
    seven = [
        C("h", "2"), C("h", "3"), C("h", "4"), C("h", "5"),
        C("h", "6"), C("h", "7"), C("s", "8"),
    ]
    assert is_seven_card_straight_flush(seven) is False


def test_seven_card_straight_flush_false_gap_in_ranks():
    seven = [
        C("h", "2"), C("h", "3"), C("h", "4"), C("h", "5"),
        C("h", "6"), C("h", "7"), C("h", "9"),  # gap at 8
    ]
    assert is_seven_card_straight_flush(seven) is False


def test_seven_card_straight_flush_with_joker_completing():
    seven = [
        JOKER,
        C("h", "3"), C("h", "4"), C("h", "5"),
        C("h", "6"), C("h", "7"), C("h", "8"),
    ]
    assert is_seven_card_straight_flush(seven) is True


def test_seven_card_straight_flush_false_when_not_7_cards():
    assert is_seven_card_straight_flush([C("h", "A")]) is False


# ─── compare_hands ───────────────────────────────────────────────────────────


def test_compare_hands_higher_first_returns_1():
    a = [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    b = [C("h", "Q"), C("s", "Q"), C("d", "K"), C("c", "9"), C("h", "5")]
    assert compare_hands(a, b) == 1


def test_compare_hands_lower_first_returns_minus_1():
    a = [C("h", "Q"), C("s", "Q"), C("d", "K"), C("c", "9"), C("h", "5")]
    b = [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    assert compare_hands(a, b) == -1


def test_compare_hands_tied_returns_0():
    """Same rank composition, different suits → tied score."""
    a = [C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"), C("h", "5")]
    b = [C("d", "K"), C("c", "K"), C("h", "Q"), C("s", "9"), C("d", "5")]
    assert compare_hands(a, b) == 0


# ─── Input validation ───────────────────────────────────────────────────────


def test_score_hand_rejects_3_cards():
    with pytest.raises(ValueError):
        score_hand([C("h", "A"), C("s", "K"), C("d", "Q")])


def test_score_hand_rejects_empty():
    with pytest.raises(ValueError):
        score_hand([])


def test_best_five_rejects_non_7_input():
    with pytest.raises(ValueError):
        best_five_card_hand([C("h", "A")])
