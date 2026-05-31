"""
showdown.py — pure showdown resolver for Texas Hold'em.

Design constraints (specs/holdem-multiplayer.md §AC-S1):
- Pure functions; no DB, no network.
- Glue between the betting engine (side pots) and the evaluator (best-5-of-7):
  given the final betting state, every non-folded seat's hole cards, and the
  community board, decide which seat(s) win each pot.
- Output is `winners_per_pot` — a list aligned 1:1 with `compute_side_pots`, so
  it feeds straight into `state.award_pots(state, winners_per_pot)`.

This module intentionally does NOT touch stacks — `award_pots` owns chip
movement. It only ranks live hands and resolves ties (co-winners chop).
"""

from __future__ import annotations

from .cards import Card
from .evaluator import rank_hand
from .state import BettingState, compute_side_pots


def decide_winners_per_pot(
    state: BettingState,
    hole_cards_by_seat: dict[int, list[Card]],
    board: list[Card],
) -> list[list[int]]:
    """Resolve every pot to its winning seat index/indices.

    `hole_cards_by_seat` maps a seat index → its two hole cards, for the
    NON-FOLDED seats reaching showdown (folded seats muck and are omitted).
    `board` is the 5 community cards (or fewer, if a sole seat wins
    uncontested — then every pot trivially has at most one contender).

    Returns a list the same length as `compute_side_pots(state)`. Each entry is
    the list of seat indices that win that pot — more than one when the best
    hand is tied (a chop). A pot with no eligible contender yields `[]`.
    """
    pots = compute_side_pots(state)

    ranks = {
        seat_idx: rank_hand(list(hole), list(board))
        for seat_idx, hole in hole_cards_by_seat.items()
        if hole and len(hole) == 2
    }

    winners_per_pot: list[list[int]] = []
    for _amount, eligible in pots:
        contenders = [i for i in eligible if i in ranks]
        if not contenders:
            winners_per_pot.append([])
            continue
        best_key = max(ranks[i].cmp_key() for i in contenders)
        winners_per_pot.append([i for i in contenders if ranks[i].cmp_key() == best_key])
    return winners_per_pot


__all__ = ["decide_winners_per_pot"]
