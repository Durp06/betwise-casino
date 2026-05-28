"""
equity.py — live equity engine for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B11..AC-B14):
- Pure functions; no DB, no network.
- Multi-way aware: equity drops sharply with more live opponents.
- Board-aware: takes a partial board (0, 3, 4, or 5 cards).
- Range-aware: opponent can be specified as known cards, random, or a hand range.
- Exact enumeration when ≤ a small handful of cards remain; Monte Carlo otherwise.
- Caller controls `iters` and `seed` for deterministic tests.

The engine returns hero's *win share* — a float in [0.0, 1.0]. A 3-way tie at
showdown contributes 1/3 to each winner's share, so equities across all live
seats sum to 1.0 in any individual showdown.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import combinations
from typing import Optional

from .cards import Card, SUITS, RANKS, remove_cards
from .evaluator import best_5_of_7
from .ranges import ALL_HANDS, combos_for, hand_str


# ─── Public types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EquityResult:
    """Return value of multi_equity. `equities` is per-seat win share."""

    equities: tuple[float, ...]
    iterations: int


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _full_deck() -> list[Card]:
    return [{"suit": s, "value": v} for s in SUITS for v in RANKS]


def _expand_range_to_combos(hand_range: set[str], blocked: list[Card]) -> list[tuple[Card, Card]]:
    """Expand a set of canonical hand strings ('AA', 'AKs') to actual 2-card
    combinations, excluding any combo that uses a blocked card.

    Returns a list of (c1, c2) tuples. Used by equity_vs_range to sample.
    """
    blocked_keys = {(c["suit"], c["value"]) for c in blocked}
    deck = [c for c in _full_deck() if (c["suit"], c["value"]) not in blocked_keys]
    combos: list[tuple[Card, Card]] = []
    for c1, c2 in combinations(deck, 2):
        hs = hand_str(c1["value"], c1["suit"], c2["value"], c2["suit"])
        if hs in hand_range:
            combos.append((c1, c2))
    return combos


# ─── Single-equity simulator ──────────────────────────────────────────────────


def equity(
    hero_hole: list[Card],
    opp_holes: list[Optional[list[Card]]],
    board: list[Card],
    iters: int = 5000,
    seed: int | None = None,
) -> float:
    """Return hero's win-share against the listed opponents on a partial board.

    Args:
        hero_hole: hero's two hole cards.
        opp_holes: one entry per opponent. Each entry is either a list of 2
            cards (known) or None (random — sampled uniformly from the
            unseen deck per iteration).
        board: partial community (0, 3, 4, or 5 cards). 1 or 2 are not legal
            in NLHE but we don't enforce that — the engine simply deals out
            to 5 cards per iteration.
        iters: number of Monte Carlo iterations. Ignored if exact enumeration
            is cheap (no random opponent holes AND board is already 4 or 5).
        seed: optional RNG seed for deterministic tests.

    Returns:
        hero's win share — a float in [0.0, 1.0]. Splits count fractionally.
    """
    if len(hero_hole) != 2:
        raise ValueError("hero_hole must have exactly 2 cards")
    for opp in opp_holes:
        if opp is not None and len(opp) != 2:
            raise ValueError("opp_holes entries must each be 2 cards or None")

    rng = random.Random(seed)
    known_cards: list[Card] = list(hero_hole) + list(board)
    for opp in opp_holes:
        if opp is not None:
            known_cards.extend(opp)

    full_deck = _full_deck()
    unseen = remove_cards(full_deck, known_cards)
    n_opp_random = sum(1 for opp in opp_holes if opp is None)
    n_board_to_deal = 5 - len(board)
    cards_to_sample = n_opp_random * 2 + n_board_to_deal

    if cards_to_sample == 0:
        # Deterministic — one showdown
        return _showdown_share(hero_hole, opp_holes, board)

    # Cheap exact enumeration: if we only need to deal a turn or river (no
    # random opponents), enumerate all combinations of the remaining cards.
    if n_opp_random == 0 and n_board_to_deal in (1, 2) and len(unseen) <= 50:
        total = 0.0
        count = 0
        for extra in combinations(unseen, n_board_to_deal):
            full_board = board + list(extra)
            total += _showdown_share(hero_hole, opp_holes, full_board)
            count += 1
        return total / count if count else 0.0

    # Monte Carlo
    total = 0.0
    for _ in range(iters):
        sample = rng.sample(unseen, cards_to_sample)
        cursor = 0
        # Assign random opponents
        full_opps: list[list[Card]] = []
        for opp in opp_holes:
            if opp is None:
                full_opps.append(list(sample[cursor:cursor + 2]))
                cursor += 2
            else:
                full_opps.append(list(opp))
        full_board = board + list(sample[cursor:cursor + n_board_to_deal])
        total += _showdown_share(hero_hole, full_opps, full_board)
    return total / iters


def _showdown_share(
    hero_hole: list[Card],
    opp_holes: list[Optional[list[Card]]],
    board: list[Card],
) -> float:
    """Showdown: compute hero's fractional win share against the opponents."""
    hero_rank = best_5_of_7(hero_hole + board)
    opp_ranks = []
    for opp in opp_holes:
        assert opp is not None  # caller has resolved random opponents already
        opp_ranks.append(best_5_of_7(list(opp) + board))
    max_rank = hero_rank
    n_tied = 1
    hero_in_tie = True
    for r in opp_ranks:
        if r.cmp_key() > max_rank.cmp_key():
            max_rank = r
            n_tied = 1
            hero_in_tie = False
        elif r.cmp_key() == max_rank.cmp_key():
            n_tied += 1
    if not hero_in_tie:
        return 0.0
    return 1.0 / n_tied


# ─── Multi-equity (per-seat shares) ───────────────────────────────────────────


def multi_equity(
    holes: list[list[Card]],
    board: list[Card],
    iters: int = 5000,
    seed: int | None = None,
) -> EquityResult:
    """Return win shares for every seat. All holes must be known.

    The shares sum to 1.0 in every individual showdown, so the returned tuple
    sums to ~1.0 across iterations.
    """
    if any(len(h) != 2 for h in holes):
        raise ValueError("Each hole must have exactly 2 cards")
    full_deck = _full_deck()
    known: list[Card] = []
    for h in holes:
        known.extend(h)
    known.extend(board)
    unseen = remove_cards(full_deck, known)
    n_board_to_deal = 5 - len(board)

    rng = random.Random(seed)
    shares = [0.0] * len(holes)

    if n_board_to_deal == 0:
        # Deterministic showdown
        ranks = [best_5_of_7(holes[i] + board) for i in range(len(holes))]
        return EquityResult(equities=_multi_showdown_shares(ranks), iterations=1)

    if n_board_to_deal in (1, 2) and len(unseen) <= 50:
        count = 0
        for extra in combinations(unseen, n_board_to_deal):
            full_board = board + list(extra)
            ranks = [best_5_of_7(holes[i] + full_board) for i in range(len(holes))]
            iter_shares = _multi_showdown_shares(ranks)
            for i, s in enumerate(iter_shares):
                shares[i] += s
            count += 1
        return EquityResult(
            equities=tuple(s / count for s in shares),
            iterations=count,
        )

    for _ in range(iters):
        sample = rng.sample(unseen, n_board_to_deal)
        full_board = board + sample
        ranks = [best_5_of_7(holes[i] + full_board) for i in range(len(holes))]
        iter_shares = _multi_showdown_shares(ranks)
        for i, s in enumerate(iter_shares):
            shares[i] += s
    return EquityResult(
        equities=tuple(s / iters for s in shares),
        iterations=iters,
    )


def _multi_showdown_shares(ranks: list) -> list[float]:
    """Compute per-seat win shares for a single showdown."""
    max_key = max(r.cmp_key() for r in ranks)
    winners = [i for i, r in enumerate(ranks) if r.cmp_key() == max_key]
    n = len(winners)
    shares = [0.0] * len(ranks)
    for w in winners:
        shares[w] = 1.0 / n
    return shares


# ─── Equity vs range ─────────────────────────────────────────────────────────


def equity_vs_range(
    hero_hole: list[Card],
    opp_range: set[str],
    board: list[Card],
    iters: int = 3000,
    seed: int | None = None,
) -> float:
    """Hero vs ONE opponent drawing uniformly from a hand range (set of
    canonical hand strings like {"AA", "AKs"}).

    Sampling is weighted by the combo count of each hand (pair = 6, suited
    = 4, offsuit = 12), so the effective range is over individual card
    combinations, not abstract hand strings.
    """
    if not opp_range:
        raise ValueError("opp_range cannot be empty")

    known_cards = list(hero_hole) + list(board)
    combos = _expand_range_to_combos(opp_range, known_cards)
    if not combos:
        # All combos blocked by hero/board cards — equity is undefined; return 0.5.
        return 0.5

    rng = random.Random(seed)
    total = 0.0
    for _ in range(iters):
        opp = rng.choice(combos)
        opp_list = [opp[0], opp[1]]
        total += equity(hero_hole, [opp_list], board, iters=1, seed=rng.randint(0, 2**32 - 1))
    return total / iters


# ─── Quick win-rate estimate (helper for archetypes) ──────────────────────────


def hero_vs_random_equity(
    hero_hole: list[Card],
    n_opponents: int,
    board: list[Card],
    iters: int = 3000,
    seed: int | None = None,
) -> float:
    """Hero's equity vs `n_opponents` random opponents on the partial board.

    Used by the coach to show "you have X% equity vs 2 random hands" — the
    underlying primitive for both Reads mode (with range substitution) and
    Odds mode (with uniform-random baseline).
    """
    opp_holes: list[Optional[list[Card]]] = [None] * n_opponents
    return equity(hero_hole, opp_holes, board, iters=iters, seed=seed)
