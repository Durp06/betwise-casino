"""
test_poker_evaluator.py — covers AC-B2..AC-B10 from specs/texas-holdem.md.

The evaluator is the heart of the equity engine, so every category gets a
test and every classic evaluator-killer scenario (wheel, Broadway, play-the-
board, counterfeited 2-pair, flush-over-flush, full-house tiebreak,
quads + kicker, category ordering) gets its own assertion.
"""
from __future__ import annotations

import pytest

from backend.game.poker.cards import Card, parse_card
from backend.game.poker.evaluator import (
    Category,
    HandRank,
    best_5_of_7,
    category_name,
    compare,
    evaluate_5,
    rank_hand,
)


def C(s: str) -> Card:
    """Shorthand: 'Ah' → Ace of hearts."""
    return parse_card(s)


def H(*strs: str) -> list[Card]:
    """Shorthand: H('Ah', 'Kh', ...) → list of cards."""
    return [C(s) for s in strs]


# ─── Category ordering (AC-B10) ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "hand_a, hand_b, name_a, name_b",
    [
        (H("Ah", "Kh", "Qh", "Jh", "Th"), H("9s", "9h", "9d", "9c", "Kh"),
         "straight flush", "quads"),
        (H("9s", "9h", "9d", "9c", "Kh"), H("9s", "9h", "9d", "Kh", "Ks"),
         "quads", "full house"),
        (H("9s", "9h", "9d", "Kh", "Ks"), H("Ah", "Jh", "9h", "6h", "3h"),
         "full house", "flush"),
        (H("Ah", "Jh", "9h", "6h", "3h"), H("9s", "8h", "7d", "6c", "5s"),
         "flush", "straight"),
        (H("9s", "8h", "7d", "6c", "5s"), H("9s", "9h", "9d", "Kh", "2s"),
         "straight", "trips"),
        (H("9s", "9h", "9d", "Kh", "2s"), H("9s", "9h", "8d", "8c", "Kh"),
         "trips", "two pair"),
        (H("9s", "9h", "8d", "8c", "Kh"), H("9s", "9h", "Kd", "5c", "2h"),
         "two pair", "pair"),
        (H("9s", "9h", "Kd", "5c", "2h"), H("As", "Kh", "9d", "6c", "3s"),
         "pair", "high card"),
    ],
)
def test_category_ordering(hand_a, hand_b, name_a, name_b):
    a = evaluate_5(hand_a)
    b = evaluate_5(hand_b)
    assert a.cmp_key() > b.cmp_key(), (
        f"Expected {name_a} > {name_b}, got {a} vs {b}"
    )
    assert compare(a, b) == 1
    assert compare(b, a) == -1


# ─── Each category — at least one positive case (AC-B2) ───────────────────────


def test_straight_flush_detected() -> None:
    hand = H("9h", "8h", "7h", "6h", "5h")
    r = evaluate_5(hand)
    assert r.category == Category.STRAIGHT_FLUSH
    assert r.kickers == (9,)


def test_royal_flush_detected_as_top_straight_flush() -> None:
    hand = H("Ah", "Kh", "Qh", "Jh", "Th")
    r = evaluate_5(hand)
    assert r.category == Category.STRAIGHT_FLUSH
    assert r.kickers == (14,)
    assert category_name(r) == "royal flush"


def test_quads_detected_with_kicker() -> None:
    hand = H("9s", "9h", "9d", "9c", "Ks")
    r = evaluate_5(hand)
    assert r.category == Category.QUADS
    assert r.kickers == (9, 13)


def test_full_house_detected_with_trip_pair_kickers() -> None:
    hand = H("9s", "9h", "9d", "Ks", "Kh")
    r = evaluate_5(hand)
    assert r.category == Category.FULL_HOUSE
    assert r.kickers == (9, 13)


def test_flush_detected_with_5_descending_kickers() -> None:
    hand = H("Ah", "Jh", "9h", "6h", "3h")
    r = evaluate_5(hand)
    assert r.category == Category.FLUSH
    assert r.kickers == (14, 11, 9, 6, 3)


def test_straight_detected_with_top_card() -> None:
    hand = H("9s", "8h", "7d", "6c", "5s")
    r = evaluate_5(hand)
    assert r.category == Category.STRAIGHT
    assert r.kickers == (9,)


def test_trips_detected_with_two_kickers() -> None:
    hand = H("9s", "9h", "9d", "Ks", "5c")
    r = evaluate_5(hand)
    assert r.category == Category.TRIPS
    assert r.kickers == (9, 13, 5)


def test_two_pair_detected_with_kicker() -> None:
    hand = H("9s", "9h", "8d", "8c", "Kh")
    r = evaluate_5(hand)
    assert r.category == Category.TWO_PAIR
    assert r.kickers == (9, 8, 13)


def test_pair_detected_with_three_kickers() -> None:
    hand = H("9s", "9h", "Kd", "7c", "3s")
    r = evaluate_5(hand)
    assert r.category == Category.PAIR
    assert r.kickers == (9, 13, 7, 3)


def test_high_card_detected_with_5_descending() -> None:
    hand = H("As", "Kh", "9d", "6c", "3s")
    r = evaluate_5(hand)
    assert r.category == Category.HIGH_CARD
    assert r.kickers == (14, 13, 9, 6, 3)


# ─── Edge cases ───────────────────────────────────────────────────────────────


def test_wheel_is_a_straight_with_top_card_5(): # AC-B3
    """A-2-3-4-5 is a straight (the wheel); top card is 5, NOT Ace."""
    hand = H("As", "5h", "4d", "3c", "2s")
    r = evaluate_5(hand)
    assert r.category == Category.STRAIGHT
    assert r.kickers == (5,)
    # And it should LOSE to 6-high straight.
    higher = evaluate_5(H("6s", "5h", "4d", "3c", "2s"))
    assert r.cmp_key() < higher.cmp_key()


def test_wheel_straight_flush_top_is_5(): # AC-B3 variant
    hand = H("Ah", "5h", "4h", "3h", "2h")
    r = evaluate_5(hand)
    assert r.category == Category.STRAIGHT_FLUSH
    assert r.kickers == (5,)


def test_broadway_straight_top_card_ace(): # AC-B4
    hand = H("Ah", "Ks", "Qd", "Jc", "Th")
    r = evaluate_5(hand)
    assert r.category == Category.STRAIGHT
    assert r.kickers == (14,)


def test_play_the_board_seven_card_eval(): # AC-B5
    """Two players, board = A-K-Q-J-T rainbow, both have meaningless hole
    cards: both evaluate to the Broadway straight. They tie."""
    board = H("As", "Kh", "Qd", "Jc", "Th")
    p1_hole = H("2s", "3s")
    p2_hole = H("4d", "7c")
    r1 = best_5_of_7(p1_hole + board)
    r2 = best_5_of_7(p2_hole + board)
    assert r1.category == Category.STRAIGHT
    assert r1.kickers == (14,)
    assert r1 == r2  # equal HandRank → tie


def test_counterfeited_two_pair(): # AC-B6
    """I hold 9-9; board is KKQQ4. My best 5 = KKQQ9 (board's higher 2-pair
    counterfeits my pair into a kicker). Player with 8-8 ties the board pair
    with the SAME kicker if their kicker matches — but with 8-8 their kicker
    is the 8, which is below my 9 — wait, the 8 is below the K kicker but
    above the kicker rank. Actually with board KKQQ4: best 5 for both is KKQQ
    + highest-other. For 9-9 hole, that's KKQQ9. For 8-8 hole, it's KKQQ8.
    The 9 kicker wins."""
    board = H("Ks", "Kh", "Qd", "Qc", "4h")
    me = H("9s", "9c")
    them = H("8s", "8c")
    me_rank = best_5_of_7(me + board)
    them_rank = best_5_of_7(them + board)
    assert me_rank.category == Category.TWO_PAIR
    assert me_rank.kickers == (13, 12, 9)
    assert them_rank.kickers == (13, 12, 8)
    assert me_rank.cmp_key() > them_rank.cmp_key()


def test_flush_over_flush_decided_by_kicker(): # AC-B7
    """Both players make a heart flush off the board. The higher non-board
    flush card wins the kicker race."""
    board = H("2h", "5h", "9h", "Jc", "3d")
    me = H("Ah", "8h")    # my flush: Ah, 9h, 8h, 5h, 2h
    them = H("Kh", "Qh")  # their flush: Kh, Qh, 9h, 5h, 2h
    me_rank = best_5_of_7(me + board)
    them_rank = best_5_of_7(them + board)
    assert me_rank.category == Category.FLUSH
    assert them_rank.category == Category.FLUSH
    assert me_rank.cmp_key() > them_rank.cmp_key()  # ace high beats king high


def test_full_house_tiebreak_by_trip_then_pair(): # AC-B8
    """Same trips, different pair sizes: higher pair wins."""
    r1 = evaluate_5(H("9s", "9h", "9d", "Ks", "Kh"))  # 9s full of Ks
    r2 = evaluate_5(H("9s", "9h", "9d", "Qs", "Qh"))  # 9s full of Qs
    assert r1.cmp_key() > r2.cmp_key()


def test_full_house_higher_trips_beats_higher_pair(): # AC-B8 stronger
    r1 = evaluate_5(H("Ts", "Th", "Td", "2s", "2h"))  # 10s full of 2s
    r2 = evaluate_5(H("9s", "9h", "9d", "As", "Ah"))  # 9s full of As
    assert r1.cmp_key() > r2.cmp_key()  # higher trips beats higher pair


def test_quads_plus_kicker_higher_kicker_wins(): # AC-B9
    r1 = evaluate_5(H("9s", "9h", "9d", "9c", "As"))
    r2 = evaluate_5(H("9s", "9h", "9d", "9c", "Ks"))
    assert r1.cmp_key() > r2.cmp_key()


# ─── 7-card best-5 picking ────────────────────────────────────────────────────


def test_best_5_of_7_picks_quads_over_pair_when_available():
    cards = H("9s", "9h", "9d", "9c", "As", "Ks", "Qs")
    r = best_5_of_7(cards)
    assert r.category == Category.QUADS
    assert r.kickers == (9, 14)


def test_best_5_of_7_picks_straight_flush_over_quads_when_available():
    # 5-6-7-8-9 of hearts + 9 of spades + 9 of clubs.
    # The straight flush 5-6-7-8-9 of hearts wins over quad-9s (9h9s9c plus 5h6h... no quads
    # because only three 9s present). Adjusted: ensure straight flush is available.
    cards = H("9h", "8h", "7h", "6h", "5h", "9s", "9c")
    r = best_5_of_7(cards)
    assert r.category == Category.STRAIGHT_FLUSH
    assert r.kickers == (9,)


def test_best_5_of_7_picks_flush_over_pair_when_available():
    cards = H("Ah", "Jh", "9h", "6h", "3h", "9c", "2s")
    r = best_5_of_7(cards)
    assert r.category == Category.FLUSH
    assert r.kickers == (14, 11, 9, 6, 3)


def test_best_5_of_7_picks_higher_straight_when_two_available():
    # Board 5-6-7-8-9; hole T-2: 6-7-8-9-T is higher than 5-6-7-8-9.
    cards = H("5s", "6h", "7d", "8c", "9s", "Th", "2c")
    r = best_5_of_7(cards)
    assert r.category == Category.STRAIGHT
    assert r.kickers == (10,)


def test_rank_hand_public_api():
    hole = H("As", "Kh")
    board = H("Qd", "Jc", "Th", "2s", "3c")
    r = rank_hand(hole, board)
    assert r.category == Category.STRAIGHT
    assert r.kickers == (14,)  # Broadway


def test_rank_hand_only_2_cards_raises():
    with pytest.raises(ValueError):
        rank_hand(H("As", "Kh"), [])


def test_rank_hand_too_many_raises():
    with pytest.raises(ValueError):
        best_5_of_7(H("As", "Kh", "Qd", "Jc", "Th", "9s", "8h", "7d"))


# ─── Compare ──────────────────────────────────────────────────────────────────


def test_compare_returns_neg_zero_pos():
    a = evaluate_5(H("Ah", "Kh", "Qh", "Jh", "Th"))  # royal
    b = evaluate_5(H("9s", "9h", "9d", "9c", "As"))  # quads
    c = evaluate_5(H("Ah", "Kh", "Qh", "Jh", "Th"))  # same as a
    assert compare(a, b) == 1
    assert compare(b, a) == -1
    assert compare(a, c) == 0


def test_category_name_includes_royal():
    royal = HandRank(Category.STRAIGHT_FLUSH, (14,))
    assert category_name(royal) == "royal flush"
    nonroyal = HandRank(Category.STRAIGHT_FLUSH, (9,))
    assert category_name(nonroyal) == "straight flush"
