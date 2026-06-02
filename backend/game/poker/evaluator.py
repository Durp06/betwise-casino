"""
evaluator.py — 7-card hand evaluator for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B2..AC-B10):
- Pure functions, no DB, no network.
- Enumerates C(N, 5) where N ∈ [5, 7] and picks the best 5-card hand.
- Returns a `(category, kicker_tuple)` HandRank where higher tuples are better.
- Handles the wheel (A-2-3-4-5 as a straight, top card 5), Broadway, play-the-
  board, counterfeited 2-pair, flush-over-flush by kicker, full-house tiebreak,
  quads + kicker, and the full category ordering.

The encoding is chosen so HandRank comparison is direct tuple comparison —
greater tuple = better hand. Categories are integers 0 (high card) through
8 (straight flush). Royal flush is simply a straight flush with high card A.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Final, NamedTuple

from .cards import Card, rank_int


# ─── Categories ───────────────────────────────────────────────────────────────


class Category:
    """Numeric category constants. Higher = stronger hand."""

    HIGH_CARD: Final[int] = 0
    PAIR: Final[int] = 1
    TWO_PAIR: Final[int] = 2
    TRIPS: Final[int] = 3
    STRAIGHT: Final[int] = 4
    FLUSH: Final[int] = 5
    FULL_HOUSE: Final[int] = 6
    QUADS: Final[int] = 7
    STRAIGHT_FLUSH: Final[int] = 8


CATEGORY_NAMES: Final[dict[int, str]] = {
    Category.HIGH_CARD: "high card",
    Category.PAIR: "pair",
    Category.TWO_PAIR: "two pair",
    Category.TRIPS: "three of a kind",
    Category.STRAIGHT: "straight",
    Category.FLUSH: "flush",
    Category.FULL_HOUSE: "full house",
    Category.QUADS: "four of a kind",
    Category.STRAIGHT_FLUSH: "straight flush",
}


class HandRank(NamedTuple):
    """Result of evaluating a 5-card hand.

    `category` is one of Category.* (higher = better). `kickers` is a length-5
    tuple of rank ints in descending order of relevance. Direct tuple comparison
    on (category, *kickers) correctly orders any two evaluated hands.
    """

    category: int
    kickers: tuple[int, ...]

    def cmp_key(self) -> tuple[int, tuple[int, ...]]:
        """Comparison key — (category, kickers) — for direct >/< comparison."""
        return (self.category, self.kickers)


def category_name(rank: HandRank) -> str:
    """Human-readable name for the hand category (e.g. 'flush', 'two pair').

    Distinguishes royal flush from other straight flushes for display polish.
    """
    if rank.category == Category.STRAIGHT_FLUSH and rank.kickers and rank.kickers[0] == 14:
        return "royal flush"
    return CATEGORY_NAMES[rank.category]


# ─── 5-card evaluation ────────────────────────────────────────────────────────

# Straights as sorted-descending rank tuples. Wheel handled specially because
# A is rank 14 in our scheme; in the wheel A acts as 1, so the top card is 5.
_STRAIGHTS_DESC: Final[list[tuple[int, ...]]] = [
    tuple(range(high, high - 5, -1))  # e.g. (14,13,12,11,10) for Broadway
    for high in range(14, 5, -1)
]
# Wheel: A-2-3-4-5 — we represent it as if its "top" is 5 for sorting
# purposes, but the cards involved are (A, 5, 4, 3, 2). For straight detection
# we check the set membership separately.
_WHEEL_RANKS: Final[frozenset[int]] = frozenset({14, 2, 3, 4, 5})


def _is_flush(cards: list[Card]) -> bool:
    return len({c["suit"] for c in cards}) == 1


def _is_straight(ranks_desc: tuple[int, ...]) -> tuple[bool, int]:
    """Return (is_straight, top_card_rank).

    `ranks_desc` is the 5 ranks sorted descending. Wheel (A,5,4,3,2) returns
    top_card_rank = 5 (per standard poker convention — the wheel is the
    lowest straight).
    """
    if ranks_desc in _STRAIGHTS_DESC:
        return True, ranks_desc[0]
    # Wheel: A,5,4,3,2 — distinct ranks form _WHEEL_RANKS
    if set(ranks_desc) == _WHEEL_RANKS:
        return True, 5
    return False, 0


def evaluate_5(hand: list[Card]) -> HandRank:
    """Evaluate exactly five cards. Used internally by best_5_of_7.

    Raises ValueError if len(hand) != 5.
    """
    if len(hand) != 5:
        raise ValueError(f"evaluate_5 expects exactly 5 cards, got {len(hand)}")

    # Sort ranks descending — this is the kicker tuple for high-card / flush.
    ranks = sorted((rank_int(c) for c in hand), reverse=True)
    ranks_tuple = tuple(ranks)
    counts = Counter(ranks)
    # `counts.most_common()` is sorted by (count desc, key desc) deterministically.
    # We rebuild the rank kickers from highest count down for paired hands.
    by_count = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    pattern = tuple(count for _, count in by_count)

    is_flush = _is_flush(hand)
    is_straight, straight_top = _is_straight(ranks_tuple)

    # ─── Straight flush ──────────────────────────────────────────────────────
    if is_flush and is_straight:
        # Kickers tuple uses the straight's top card padded — comparison among
        # straight flushes is by top card only.
        return HandRank(Category.STRAIGHT_FLUSH, (straight_top,))

    # ─── Quads ───────────────────────────────────────────────────────────────
    if pattern == (4, 1):
        quad_rank = by_count[0][0]
        kicker = by_count[1][0]
        return HandRank(Category.QUADS, (quad_rank, kicker))

    # ─── Full house ──────────────────────────────────────────────────────────
    if pattern == (3, 2):
        trip_rank = by_count[0][0]
        pair_rank = by_count[1][0]
        return HandRank(Category.FULL_HOUSE, (trip_rank, pair_rank))

    # ─── Flush ───────────────────────────────────────────────────────────────
    if is_flush:
        return HandRank(Category.FLUSH, ranks_tuple)

    # ─── Straight ────────────────────────────────────────────────────────────
    if is_straight:
        return HandRank(Category.STRAIGHT, (straight_top,))

    # ─── Trips ───────────────────────────────────────────────────────────────
    if pattern == (3, 1, 1):
        trip_rank = by_count[0][0]
        kickers = tuple(r for r, _ in by_count[1:])
        return HandRank(Category.TRIPS, (trip_rank, *kickers))

    # ─── Two pair ────────────────────────────────────────────────────────────
    if pattern == (2, 2, 1):
        # by_count groups by count first then rank desc; the two pair entries
        # are the first two — order them by rank desc.
        pair_ranks = sorted((by_count[0][0], by_count[1][0]), reverse=True)
        kicker = by_count[2][0]
        return HandRank(Category.TWO_PAIR, (pair_ranks[0], pair_ranks[1], kicker))

    # ─── Pair ────────────────────────────────────────────────────────────────
    if pattern == (2, 1, 1, 1):
        pair_rank = by_count[0][0]
        kickers = tuple(r for r, _ in by_count[1:])
        return HandRank(Category.PAIR, (pair_rank, *kickers))

    # ─── High card ───────────────────────────────────────────────────────────
    return HandRank(Category.HIGH_CARD, ranks_tuple)


# ─── 7-card evaluation (the public API) ───────────────────────────────────────


def best_5_of_7(cards: list[Card]) -> HandRank:
    """Pick the best 5-card hand from 5–7 cards.

    Enumerates C(N, 5) ∈ {1, 6, 21} sub-hands and returns the max.
    """
    if len(cards) < 5 or len(cards) > 7:
        raise ValueError(
            f"best_5_of_7 expects 5–7 cards (2 hole + 0/3/4/5 board), got {len(cards)}"
        )
    best: HandRank | None = None
    for combo in combinations(cards, 5):
        rank = evaluate_5(list(combo))
        if best is None or rank.cmp_key() > best.cmp_key():
            best = rank
    assert best is not None  # combinations of 5 over ≥5 cards is non-empty
    return best


def rank_hand(hole: list[Card], board: list[Card]) -> HandRank:
    """Public entry point — hole + community board → HandRank."""
    return best_5_of_7(hole + board)


def compare(a: HandRank, b: HandRank) -> int:
    """Return -1, 0, or 1 indicating a < b, a == b, a > b.

    Tuple comparison on (category, kickers) — natural ordering.
    """
    ka, kb = a.cmp_key(), b.cmp_key()
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0
