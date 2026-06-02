"""
test_pai_gow_house_way.py — Foxwoods house way coverage.

One test per rule cluster, plus the load-bearing edge cases the round-6
review flagged:
- high-quad split foul-pass (KK | KK + kickers)
- two-pair split vs keep with Ace-kicker rule
- full-house split (pair → front, trips → back)
- trips never split (Foxwoods, including trip aces)
- legal-split invariant for every produced split (back >= front under §7.3)
"""
from __future__ import annotations

import pytest

import random

from backend.game.pai_gow.cards import JOKER, card_rank, create_deck
from backend.game.pai_gow.evaluator import score_hand
from backend.game.pai_gow.house_way import _resolve_joker_as_ace, foxwoods


_SUIT_SHORT = {"h": "hearts", "d": "diamonds", "c": "clubs", "s": "spades"}


def C(suit, value):
    return {"suit": _SUIT_SHORT.get(suit, suit), "value": value}


def _ranks_sorted(cards):
    return sorted(card_rank(c) for c in cards)


def _is_legal_split(front, back):
    """back STRICTLY > front under §7.3 unified ordering (equality is also
    legal per round-6 §7.4 strict-foul rule, but house way never produces
    a strict equality — it always lands clearly back > front)."""
    return score_hand(back) >= score_hand(front)


# ─── Rule 1: Straight flush ──────────────────────────────────────────────────


def test_rule1_straight_flush_keeps_in_back():
    """5-card SF → back; 2 leftover → front."""
    cards = [
        C("h", "9"), C("h", "8"), C("h", "7"), C("h", "6"), C("h", "5"),
        C("s", "K"), C("c", "Q"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [12, 13]   # Q, K
    assert _ranks_sorted(back) == [5, 6, 7, 8, 9]
    assert _is_legal_split(front, back)


def test_rule1_royal_flush_keeps_in_back():
    cards = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "10"),
        C("s", "5"), C("c", "3"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [3, 5]
    assert _ranks_sorted(back) == [10, 11, 12, 13, 14]
    assert _is_legal_split(front, back)


def test_rule1_seven_card_sf_picks_highest_5_for_back():
    """A-K-Q-J-10-9-8 all hearts → broadway in back, 9♥ + 8♥ in front."""
    cards = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"),
        C("h", "10"), C("h", "9"), C("h", "8"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [8, 9]
    assert _ranks_sorted(back) == [10, 11, 12, 13, 14]
    assert _is_legal_split(front, back)


# ─── Rule 2: Four of a kind (the round-6 review highlight) ───────────────────


def test_rule2_low_quads_keep_in_back():
    """Quads 2-6 → KEEP. Quads + highest kicker in back; next 2 highest in front."""
    cards = [
        C("h", "4"), C("s", "4"), C("d", "4"), C("c", "4"),
        C("h", "K"), C("s", "J"), C("c", "5"),
    ]
    front, back = foxwoods(cards)
    # Quads + K in back; J + 5 in front
    assert _ranks_sorted(back) == [4, 4, 4, 4, 13]
    assert _ranks_sorted(front) == [5, 11]
    assert _is_legal_split(front, back)


def test_rule2_medium_quads_with_ace_keep():
    """Quads 7-10 with an Ace kicker → KEEP. Ace doesn't force a split."""
    cards = [
        C("h", "9"), C("s", "9"), C("d", "9"), C("c", "9"),
        C("h", "A"), C("s", "J"), C("c", "5"),
    ]
    front, back = foxwoods(cards)
    # Quads + A → back; J + 5 → front
    assert _ranks_sorted(back) == [9, 9, 9, 9, 14]
    assert _ranks_sorted(front) == [5, 11]
    assert _is_legal_split(front, back)


def test_rule2_medium_quads_no_ace_split():
    """Quads 7-10 with no Ace kicker → SPLIT into two pairs."""
    cards = [
        C("h", "9"), C("s", "9"), C("d", "9"), C("c", "9"),
        C("h", "J"), C("s", "5"), C("c", "3"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [9, 9]
    # back: pair-9 + 3 highest non-quads = 9, 9, J, 5, 3
    assert _ranks_sorted(back) == [3, 5, 9, 9, 11]
    assert _is_legal_split(front, back)


def test_rule2_HIGH_QUAD_split_passes_foul_check_round4_round6_catch():
    """The round-4 / round-6 review pin: 4 K's + kickers split into KK | KK +
    3 kickers. Both halves look like 'pair of K' by category, but the back
    wins via §7.3 kicker tiebreak (front has length-2 score tuple, back has
    length-5). LEGAL, not foul.
    """
    cards = [
        C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"),
        C("h", "J"), C("s", "5"), C("c", "3"),
    ]
    front, back = foxwoods(cards)
    # Front: pair of K
    assert _ranks_sorted(front) == [13, 13]
    # Back: pair of K + J, 5, 3 kickers
    assert _ranks_sorted(back) == [3, 5, 11, 13, 13]
    # Most important: this split must NOT foul (back > front via kickers).
    assert _is_legal_split(front, back)
    # And specifically: back is one-pair-with-kickers; front is one-pair-no-kicker.
    assert score_hand(back) > score_hand(front)


def test_rule2_quad_aces_split():
    """4 Aces → SPLIT (high-quad rule). Pair-A front; pair-A + 3 kickers back."""
    cards = [
        C("h", "A"), C("s", "A"), C("d", "A"), C("c", "A"),
        C("h", "K"), C("s", "J"), C("c", "5"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [14, 14]
    assert _ranks_sorted(back) == [5, 11, 13, 14, 14]
    assert _is_legal_split(front, back)


# ─── Rule 3: Full house (always split) ───────────────────────────────────────


def test_rule3_full_house_pair_to_front_trips_to_back():
    """Full house → SPLIT. Pair (highest pair-rank) → front; trips → back +
    2 highest other kickers. Back becomes three-of-a-kind; front pair.
    """
    cards = [
        C("h", "9"), C("s", "9"), C("d", "9"),
        C("c", "K"), C("h", "K"),
        C("s", "J"), C("c", "7"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [13, 13]  # pair K to front
    assert _ranks_sorted(back) == [7, 9, 9, 9, 11]  # trips 9 + J, 7
    assert _is_legal_split(front, back)


def test_rule3_two_trips_treated_as_full_house():
    """Two trips (e.g., 999 + 666 + kicker): higher trips in back, lower
    trips' pair → front, low trips' 3rd card joins back as kicker."""
    cards = [
        C("h", "9"), C("s", "9"), C("d", "9"),
        C("h", "6"), C("s", "6"), C("d", "6"),
        C("c", "K"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [6, 6]
    # back: 3 nines + 1 six + 1 K = trips of 9 with 6 and K kickers
    assert _ranks_sorted(back) == [6, 9, 9, 9, 13]
    assert _is_legal_split(front, back)


# ─── Rule 4: Three pairs ─────────────────────────────────────────────────────


def test_rule4_three_pairs_highest_pair_to_front():
    """3 pairs: highest pair → front; other 2 pairs + 1 kicker → back as two-pair."""
    cards = [
        C("h", "A"), C("s", "A"),
        C("d", "K"), C("c", "K"),
        C("h", "5"), C("s", "5"),
        C("c", "J"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [14, 14]  # pair of A
    assert _ranks_sorted(back) == [5, 5, 11, 13, 13]  # 2 pair K and 5 + J kicker
    assert _is_legal_split(front, back)


# ─── Rule 5: Flush ───────────────────────────────────────────────────────────


def test_rule5_flush_keeps_in_back():
    cards = [
        C("h", "K"), C("h", "Q"), C("h", "9"), C("h", "5"), C("h", "2"),
        C("s", "7"), C("c", "3"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [3, 7]
    assert _ranks_sorted(back) == [2, 5, 9, 12, 13]
    assert _is_legal_split(front, back)


# ─── Rule 6: Straight ────────────────────────────────────────────────────────


def test_rule6_straight_keeps_in_back():
    cards = [
        C("h", "9"), C("s", "8"), C("d", "7"), C("c", "6"), C("h", "5"),
        C("s", "K"), C("c", "2"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [2, 13]
    assert _ranks_sorted(back) == [5, 6, 7, 8, 9]
    assert _is_legal_split(front, back)


def test_rule6_wheel_straight_keeps_in_back_over_low_straight():
    """A-2-3-4-5-6-7: prefer the WHEEL (rank 9 per §7.2) over 7-high (rank 2).

    Wheel rank > 7-high rank in PG, so back picks the wheel and front gets
    the unused 2 cards (6 and 7).
    """
    cards = [
        C("h", "A"), C("s", "2"), C("d", "3"), C("c", "4"),
        C("h", "5"), C("s", "6"), C("c", "7"),
    ]
    front, back = foxwoods(cards)
    # Wheel cards 14, 5, 4, 3, 2 → back
    assert _ranks_sorted(back) == [2, 3, 4, 5, 14]
    # Front gets 6 and 7 (unused)
    assert _ranks_sorted(front) == [6, 7]
    assert _is_legal_split(front, back)


# ─── Rule 7: Three of a kind (Foxwoods: ALWAYS keep, never split) ────────────


def test_rule7_trips_keep_in_back():
    cards = [
        C("h", "9"), C("s", "9"), C("d", "9"),
        C("c", "K"), C("h", "J"), C("s", "5"), C("c", "3"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [11, 13]  # K, J
    assert _ranks_sorted(back) == [3, 5, 9, 9, 9]
    assert _is_legal_split(front, back)


def test_rule7_trip_aces_DO_NOT_split():
    """Foxwoods variant: even trip aces stay in back (some PG variants split;
    Foxwoods does not — splitting trip aces would foul the hand)."""
    cards = [
        C("h", "A"), C("s", "A"), C("d", "A"),
        C("c", "K"), C("h", "J"), C("s", "9"), C("c", "7"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [11, 13]  # K, J
    assert _ranks_sorted(back) == [7, 9, 14, 14, 14]
    assert _is_legal_split(front, back)


# ─── Rule 8: Two pair ────────────────────────────────────────────────────────


def test_rule8_two_pair_both_low_keep_together():
    """Both pairs ≤ 6 → KEEP. 2 pair → back + 1 lowest non-pair kicker;
    2 highest non-pair → front."""
    cards = [
        C("h", "6"), C("s", "6"),
        C("d", "4"), C("c", "4"),
        C("h", "K"), C("s", "Q"), C("c", "J"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [12, 13]  # K Q
    # back: 6 6 4 4 J (J is lowest non-pair → kicker)
    assert _ranks_sorted(back) == [4, 4, 6, 6, 11]
    assert _is_legal_split(front, back)


def test_rule8_two_pair_both_high_split():
    """Both pairs ≥ 7 → SPLIT. Higher pair + 3 highest non-pair → back;
    lower pair → front."""
    cards = [
        C("h", "K"), C("s", "K"),
        C("d", "9"), C("c", "9"),
        C("h", "J"), C("s", "5"), C("c", "3"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [9, 9]  # lower pair → front
    assert _ranks_sorted(back) == [3, 5, 11, 13, 13]  # K K + J 5 3
    assert _is_legal_split(front, back)


def test_rule8_two_pair_mixed_with_ace_kicker_keeps_together():
    """One low pair + one high pair + Ace kicker → KEEP. Both pairs to back +
    lowest non-pair-non-ace kicker; Ace + next highest → front."""
    cards = [
        C("h", "K"), C("s", "K"),
        C("d", "4"), C("c", "4"),
        C("h", "A"), C("s", "9"), C("c", "5"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [9, 14]  # A, 9
    assert _ranks_sorted(back) == [4, 4, 5, 13, 13]  # K K 4 4 5
    assert _is_legal_split(front, back)


def test_rule8_two_pair_mixed_no_ace_splits():
    """One low pair + one high pair + NO Ace → SPLIT. Higher pair to back +
    3 highest non-pair; lower pair → front."""
    cards = [
        C("h", "K"), C("s", "K"),
        C("d", "4"), C("c", "4"),
        C("h", "J"), C("s", "9"), C("c", "5"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [4, 4]  # lower pair → front
    assert _ranks_sorted(back) == [5, 9, 11, 13, 13]  # K K + J 9 5
    assert _is_legal_split(front, back)


# ─── Rule 9: One pair ────────────────────────────────────────────────────────


def test_rule9_one_pair_pair_to_back_high_kickers_to_front():
    """Pair → back + 3 LOWEST non-pair kickers; 2 HIGHEST non-pair → front."""
    cards = [
        C("h", "K"), C("s", "K"),
        C("d", "J"), C("c", "9"), C("h", "7"), C("s", "5"), C("c", "3"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [9, 11]  # J, 9 (2 highest non-pair)
    assert _ranks_sorted(back) == [3, 5, 7, 13, 13]  # K K + 3 lowest
    assert _is_legal_split(front, back)


# ─── Rule 10: No pair (high card hand) ───────────────────────────────────────


def test_rule10_no_pair_high_to_back_second_third_to_front():
    """Highest card + 4 lowest → back; 2nd + 3rd highest → front."""
    cards = [
        C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "J"),
        C("h", "9"), C("s", "7"), C("c", "5"),
    ]
    front, back = foxwoods(cards)
    assert _ranks_sorted(front) == [12, 13]  # K, Q
    # back: A + J 9 7 5 (highest + 4 lowest)
    assert _ranks_sorted(back) == [5, 7, 9, 11, 14]
    assert _is_legal_split(front, back)


# ─── Joker handling (v1 simplification: joker = Ace) ─────────────────────────


def test_joker_resolved_as_ace_in_no_pair_hand():
    """Joker + K Q J 9 7 5 → joker becomes A. Then high-card-A hand:
    back = A J 9 7 5, front = K Q.
    """
    cards = [
        JOKER, C("s", "K"), C("d", "Q"), C("c", "J"),
        C("h", "9"), C("s", "7"), C("c", "5"),
    ]
    front, back = foxwoods(cards)
    # After joker→Ace: A K Q J 9 7 5 (same as the no-pair test above)
    assert _ranks_sorted(front) == [12, 13]
    assert _ranks_sorted(back) == [5, 7, 9, 11, 14]
    assert _is_legal_split(front, back)


def test_joker_pairs_with_existing_ace():
    """Joker + A + 5 others → joker becomes A, forms pair of Aces."""
    cards = [
        JOKER, C("h", "A"), C("s", "K"), C("d", "J"),
        C("c", "9"), C("h", "7"), C("s", "5"),
    ]
    front, back = foxwoods(cards)
    # After joker→Ace: A A K J 9 7 5 = pair of A. Rule 9: pair → back + 3
    # lowest kickers (9, 7, 5); 2 highest non-pair (K, J) → front.
    assert _ranks_sorted(front) == [11, 13]
    assert _ranks_sorted(back) == [5, 7, 9, 14, 14]
    assert _is_legal_split(front, back)


# ─── Universal legal-split invariant ────────────────────────────────────────


@pytest.mark.parametrize("cards", [
    # Random sample across categories — house way must NEVER produce a foul.
    [C("h", "A"), C("s", "A"), C("d", "K"), C("c", "K"), C("h", "Q"), C("s", "Q"), C("c", "J")],   # 3 pairs
    [C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"), C("h", "J"), C("s", "5"), C("c", "3")],   # high quads
    [C("h", "4"), C("s", "4"), C("d", "4"), C("c", "4"), C("h", "Q"), C("s", "9"), C("c", "3")],   # low quads
    [C("h", "9"), C("s", "9"), C("d", "9"), C("c", "K"), C("h", "K"), C("s", "5"), C("c", "3")],   # full house
    [C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "10"), C("s", "5"), C("c", "3")],  # royal flush
    [C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "J"), C("h", "9"), C("s", "7"), C("c", "5")],   # no pair
])
def test_legal_split_invariant_no_foul_ever(cards):
    """House way must NEVER foul. score_hand(back) >= score_hand(front) for
    every reachable input. This is the universal safety net."""
    front, back = foxwoods(cards)
    assert score_hand(back) >= score_hand(front), (
        f"FOUL: front={front} back={back} "
        f"score_front={score_hand(front)} score_back={score_hand(back)}"
    )


# ─── Input validation ───────────────────────────────────────────────────────


def test_house_way_rejects_non_7_cards():
    with pytest.raises(ValueError):
        foxwoods([C("h", "A")])
    with pytest.raises(ValueError):
        foxwoods([C("h", str(i)) if i < 10 else C("h", "K") for i in range(2, 10)])  # 8 cards


# ─── Randomized fuzz sweep (300 seeded deals) ────────────────────────────────


def _card_key(c):
    return (c["suit"], c["value"])


def test_house_way_fuzz_300_random_seeds():
    """Fuzz over 300 seeded random 7-card deals from the 53-card deck.

    For every hand, foxwoods() must satisfy three invariants:
      (a) No foul:    score_hand(back) >= score_hand(front) under §7.3.
      (b) Exact size: len(front) == 2 and len(back) == 5.
      (c) Multiset preservation: the 7 cards in (front + back), compared by
          (suit, value), exactly match the input AFTER joker resolution.
          (Joker is substituted to Ace-of-an-unused-suit before dispatch —
          see _resolve_joker_as_ace docstring.)

    Seeded `random.Random(seed)` means deterministic — same 300 hands on
    every run. Any future house-way change that fouls or loses a card on
    ANY of the 300 hands surfaces immediately.
    """
    for seed in range(300):
        rng = random.Random(seed)
        deck = create_deck()  # 53 cards (52 + joker)
        rng.shuffle(deck)
        cards = deck[:7]

        front, back = foxwoods(cards)

        # (a) No foul
        assert score_hand(back) >= score_hand(front), (
            f"FOUL on seed={seed}: front={front} back={back} "
            f"score_front={score_hand(front)} score_back={score_hand(back)} "
            f"input={cards}"
        )

        # (b) Exact card counts
        assert len(front) == 2, (
            f"seed={seed}: front size={len(front)}, expected 2; input={cards}"
        )
        assert len(back) == 5, (
            f"seed={seed}: back size={len(back)}, expected 5; input={cards}"
        )

        # (c) Multiset preservation (after joker resolution)
        resolved_input = _resolve_joker_as_ace(cards)
        input_keys = sorted(_card_key(c) for c in resolved_input)
        output_keys = sorted(_card_key(c) for c in (front + back))
        assert input_keys == output_keys, (
            f"seed={seed}: multiset mismatch.\n"
            f"  input (post-joker resolution): {input_keys}\n"
            f"  output (front + back):         {output_keys}\n"
            f"  raw input:                     {cards}"
        )
