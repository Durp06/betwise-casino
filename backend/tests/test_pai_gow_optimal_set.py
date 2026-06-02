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


def test_evaluate_split_order_independent_via_canonical_sort_round6_fix():
    """The round-6 #5 catch: comparing `[K♥, K♠]` to `[K♠, K♥]` as raw lists
    would falsely flag the player as suboptimal and reset the streak. The
    canonical-sort comparison must treat them as equivalent.
    """
    cards = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    optimal = find_optimal(cards)
    # Reverse the order of each half — equivalent hand under §12.5
    player_front = list(reversed(optimal.front))
    player_back = list(reversed(optimal.back))
    result = evaluate_split(cards, player_front, player_back)
    assert result.is_optimal is True
    assert result.ev_loss_unit_cents == 0


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
