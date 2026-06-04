"""
test_pai_gow_optimal_set.py — Chipy's optimal split + EV evaluation.

Per spec §12.2 (Chipy tool calls):
- `find_optimal(cards)` returns (front, back, ev_unit_cents, reasoning_key).
- `evaluate_split(cards, player_front, player_back)` returns whether the
  player's split matched optimal, applying the §12.5 canonical-sort
  comparison so input order doesn't affect was_optimal.

v1 ships with an empty Wong-deviation table — `find_optimal` returns
`house_way`'s split with `ev_unit_cents=0` and `reasoning_key="house_way"`
for every hand. The API surface is in place for v2 to add deviations.

The load-bearing contract for Phase 4: `evaluate_split` is the authoritative
oracle for `was_optimal` / streak updates (per the user's reminder — NOT
`house_way` directly, so future deviations route through this layer cleanly).
"""
from __future__ import annotations

import pytest

from backend.game.pai_gow.cards import JOKER
from backend.game.pai_gow.house_way import foxwoods
from backend.game.pai_gow.optimal_set import (
    OptimalSplit,
    SplitEvaluation,
    evaluate_split,
    find_optimal,
)


_SUIT_SHORT = {"h": "hearts", "d": "diamonds", "c": "clubs", "s": "spades"}


def C(suit: str, value: str) -> dict:
    return {"suit": _SUIT_SHORT.get(suit, suit), "value": value}


# ─── find_optimal — v1 mirrors house_way ─────────────────────────────────────


def test_find_optimal_returns_house_way_split_in_v1():
    """v1 deviation table is empty → optimal split == house_way split for
    every hand. ev_unit_cents=0, reasoning_key='house_way'.
    """
    cards = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    optimal = find_optimal(cards)
    hw_front, hw_back = foxwoods(cards)

    assert optimal.front == hw_front
    assert optimal.back == hw_back
    assert optimal.ev_unit_cents == 0
    assert optimal.reasoning_key == "house_way"


def test_find_optimal_high_quad_split_matches_house_way():
    """The round-4 high-quad case — optimal mirrors house_way's KK | KK+kickers."""
    cards = [
        C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"),
        C("h", "J"), C("s", "5"), C("c", "3"),
    ]
    optimal = find_optimal(cards)
    hw_front, hw_back = foxwoods(cards)
    assert optimal.front == hw_front
    assert optimal.back == hw_back


def test_find_optimal_returns_OptimalSplit_dataclass():
    """API contract — return type is OptimalSplit, not a tuple."""
    cards = [
        C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "J"),
        C("h", "9"), C("s", "7"), C("c", "5"),
    ]
    result = find_optimal(cards)
    assert isinstance(result, OptimalSplit)
    assert len(result.front) == 2
    assert len(result.back) == 5
    assert isinstance(result.ev_unit_cents, int)
    assert isinstance(result.reasoning_key, str)


def test_find_optimal_rejects_non_7_cards():
    with pytest.raises(ValueError):
        find_optimal([C("h", "A")])


# ─── evaluate_split — was_optimal canonical-sort comparison (§12.5) ──────────


def test_evaluate_split_matching_optimal_returns_is_optimal_true():
    cards = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    optimal = find_optimal(cards)
    result = evaluate_split(cards, optimal.front, optimal.back)
    assert result.is_optimal is True
    assert result.ev_loss_unit_cents == 0


def test_evaluate_split_order_independent_via_score_hand_round6_fix():
    """Round-6 #5: comparing `[K♥, K♠]` to `[K♠, K♥]` as raw lists would
    falsely flag the player as suboptimal and reset the streak. With the
    round-7 score-based comparison, order independence is free because
    `score_hand` sorts ranks internally.
    """
    cards = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    optimal = find_optimal(cards)
    # Reverse the order of each half — same EV.
    player_front = list(reversed(optimal.front))
    player_back = list(reversed(optimal.back))
    result = evaluate_split(cards, player_front, player_back)
    assert result.is_optimal is True
    assert result.ev_loss_unit_cents == 0


def test_evaluate_split_quad_K_different_K_choice_is_EV_equivalent_round7_catch():
    """**Round-7 catch**: with 4 K's in hand, ALL 4 are interchangeable for
    the front pair. House way picks (say) K♣K♦ for the front; player picks
    K♥K♠ instead. Both are "pair of K" — score (ONE_PAIR, 13) — same EV,
    same win probability against any dealer hand.

    The previous card-identity comparison would have said "wrong cards" and
    reset the player's streak. This breaks the 'measurably better player'
    gold-feature thesis because the player IS playing optimally and the
    streak counter should reflect that.
    """
    cards = [
        C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"),
        C("h", "J"), C("s", "5"), C("c", "3"),
    ]
    optimal = find_optimal(cards)
    # Sanity: house_way picked the lowest-sorted 2 K's for front.
    assert len(optimal.front) == 2 and len(optimal.back) == 5

    # Player picks the OTHER 2 K's for front (the ones house_way put in back).
    optimal_front_cards = {(c["suit"], c["value"]) for c in optimal.front}
    all_K = [c for c in cards if c["value"] == "K"]
    player_front = [c for c in all_K if (c["suit"], c["value"]) not in optimal_front_cards]
    # Player's back: the other 2 K's + the 3 non-K kickers.
    non_K = [c for c in cards if c["value"] != "K"]
    player_back = list(optimal.front) + non_K
    # Defensive: sizes should match.
    assert len(player_front) == 2
    assert len(player_back) == 5

    result = evaluate_split(cards, player_front, player_back)
    assert result.is_optimal is True, (
        f"EV-equivalent K-swap should match. "
        f"player_front_score={result}; optimal_front={optimal.front}"
    )
    assert result.ev_loss_unit_cents == 0


def test_evaluate_split_straight_using_either_of_two_same_rank_cards_is_EV_equivalent():
    """When a hand has two cards of the same rank and one fills a straight,
    swapping which one goes into the straight (vs leftover) is EV-equivalent.

    Hand: 9♥ 9♦ 8♣ 7♣ 6♣ 5♣ K♠ — straight 9-5; one 9 in straight, one in
    front. Whether the 9♥ or 9♦ fills the straight, the split scores
    identically: back = (STRAIGHT, 4), front depends but same in both cases.
    """
    cards = [
        C("h", "9"), C("d", "9"), C("c", "8"), C("c", "7"),
        C("c", "6"), C("c", "5"), C("s", "K"),
    ]
    optimal = find_optimal(cards)

    # Identify the 9 in the optimal back (used in the straight) and the 9 in
    # front/elsewhere. Player swaps which 9 goes where.
    nines_in_back = [c for c in optimal.back if c["value"] == "9"]
    nines_in_front_or_back = [c for c in cards if c["value"] == "9"]

    # Skip the swap test if both 9's ended up in the same half (no swap possible).
    if len(nines_in_back) != 1:
        pytest.skip("Both 9's in same half; no meaningful swap test")

    in_back_9 = nines_in_back[0]
    out_back_9 = next(c for c in nines_in_front_or_back if c is not in_back_9)

    # Build player split by swapping the two 9's.
    player_back = [out_back_9 if c is in_back_9 else c for c in optimal.back]
    player_front = [in_back_9 if c is out_back_9 else c for c in optimal.front]

    result = evaluate_split(cards, player_front, player_back)
    assert result.is_optimal is True


def test_evaluate_split_deviating_returns_is_optimal_false():
    """Construct a deliberately wrong split — wrong front and back → not optimal."""
    cards = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    # Optimal: front=[Q, 9], back=[K, K, 5, 3, 2] (one pair rule).
    # Wrong: split the K's — front=[K, K], back=[Q, 9, 5, 3, 2] (suboptimal,
    # and arguably fouls — pair-K front vs Q-high back).
    wrong_front = [C("h", "K"), C("s", "K")]
    wrong_back = [C("d", "Q"), C("c", "9"), C("h", "5"), C("s", "3"), C("c", "2")]
    result = evaluate_split(cards, wrong_front, wrong_back)
    assert result.is_optimal is False


def test_evaluate_split_exposes_optimal_for_chipy_explanation():
    """Result includes the optimal split + reasoning key so Chipy can show
    'should have been ...' in the post-play explanation."""
    cards = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    wrong_front = [C("h", "K"), C("s", "K")]
    wrong_back = [C("d", "Q"), C("c", "9"), C("h", "5"), C("s", "3"), C("c", "2")]
    result = evaluate_split(cards, wrong_front, wrong_back)
    assert isinstance(result, SplitEvaluation)
    optimal = find_optimal(cards)
    assert result.optimal_front == optimal.front
    assert result.optimal_back == optimal.back
    assert result.reasoning_key == optimal.reasoning_key


def test_evaluate_split_works_for_joker_hands():
    """Joker hands go through evaluate_split the same way — joker is
    resolved during house_way, and the player's optimal-match check uses
    the resolved cards.
    """
    cards = [
        JOKER, C("s", "K"), C("d", "Q"), C("c", "J"),
        C("h", "9"), C("s", "7"), C("c", "5"),
    ]
    optimal = find_optimal(cards)
    result = evaluate_split(cards, optimal.front, optimal.back)
    assert result.is_optimal is True


def test_evaluate_split_rejects_non_7_cards():
    with pytest.raises(ValueError):
        evaluate_split([C("h", "A")], [], [])


# ─── Deviation table (extensible for v2) ────────────────────────────────────


def test_v1_deviation_table_is_empty():
    """v1 ships with an empty deviation table. Adding a deviation should be a
    localized change to optimal_set._DEVIATIONS — doesn't require touching
    house_way, state.py, or any caller. Verified here so a v2 addition is a
    conscious decision, not an accident.
    """
    from backend.game.pai_gow.optimal_set import _DEVIATIONS
    assert _DEVIATIONS == {}


# ─── Phase 4 contract reminder ──────────────────────────────────────────────


def test_phase4_contract_was_optimal_uses_optimal_set_not_house_way():
    """The Phase 4 streak/was_optimal layer MUST route through evaluate_split
    (which compares against find_optimal), NOT directly against foxwoods.

    Why this matters: when v2 adds Wong deviations, find_optimal will
    deviate from foxwoods on specific hand patterns. If state.py compares
    against foxwoods, the player who correctly follows Chipy's deviation
    would be flagged as suboptimal — breaking the 'measurably better player'
    thesis.

    This is a smoke test that the API surface supports the right layering:
    evaluate_split returns is_optimal AND the optimal split came from
    find_optimal (which v2 can deviate from house_way), not from foxwoods.
    """
    cards = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    optimal = find_optimal(cards)
    hw_front, hw_back = foxwoods(cards)
    # v1: they happen to match.
    assert optimal.front == hw_front
    assert optimal.back == hw_back
    # The contract: evaluate_split's optimal source is find_optimal, not
    # foxwoods. (When v2 deviates, optimal.front/back diverges from
    # hw_front/hw_back; evaluate_split still produces correct was_optimal.)
    result = evaluate_split(cards, hw_front, hw_back)
    assert result.optimal_front == optimal.front  # not just hw_front
    assert result.optimal_back == optimal.back
