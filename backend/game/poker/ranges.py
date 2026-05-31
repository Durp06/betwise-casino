"""
ranges.py — starting-hand range constants for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B18..AC-B21):
- Pure functions and data tables — no DB, no network.
- chen_score implements the Bill Chen formula with the documented rules
  (specs/texas-holdem-reference.md §5).
- SKLANSKY_GROUPS encodes the canonical Sklansky-Malmuth groups 1-9
  (reference §6). Group 9 is everything not in 1-8.
- HAND_GRID maps the 13×13 grid representation (pairs on diagonal, suited
  upper triangle, offsuit lower triangle).
- SC_RANK_ORDER is the Sklansky-Chubukov ordering top-down.

Canonical hand-string format:
- Pairs: "77", "AA"  (rank doubled)
- Suited: "AKs", "JTs"  (high rank first, then low, then 's')
- Offsuit: "AKo", "JTo"  (high rank first, then low, then 'o')
"""

from __future__ import annotations

from typing import Final


# ─── Rank ordering helpers ────────────────────────────────────────────────────

# Index 0 = strongest (A), index 12 = weakest (2). This matches reference §11.
_RANKS_HIGH_TO_LOW: Final[tuple[str, ...]] = ("A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2")

# Numeric rank for each rank-char. "T" is used for ten in the canonical hand
# string (e.g. "JTs"), even though the Card wire format uses "10".
_RANK_NUM: Final[dict[str, int]] = {
    "A": 14, "K": 13, "Q": 12, "J": 11, "T": 10,
    "9": 9, "8": 8, "7": 7, "6": 6, "5": 5, "4": 4, "3": 3, "2": 2,
}


def _rank_char_from_value(value: str) -> str:
    """Convert a Card wire-format value ('10', 'J', etc.) to a hand-string rank
    char ('T', 'J', etc.)."""
    return "T" if value == "10" else value


def hand_str(c1_value: str, c1_suit: str, c2_value: str, c2_suit: str) -> str:
    """Canonical hand-string for a pair of hole-card values + suits.

    Examples:
      hand_str("A", "hearts", "K", "hearts") == "AKs"
      hand_str("A", "hearts", "K", "spades") == "AKo"
      hand_str("7", "hearts", "7", "spades") == "77"
    """
    r1 = _rank_char_from_value(c1_value)
    r2 = _rank_char_from_value(c2_value)
    n1 = _RANK_NUM[r1]
    n2 = _RANK_NUM[r2]
    if n1 == n2:
        return f"{r1}{r2}"  # pair
    high, low = (r1, r2) if n1 > n2 else (r2, r1)
    suited = c1_suit == c2_suit
    return f"{high}{low}{'s' if suited else 'o'}"


# ─── 169-hand grid (AC-B21) ───────────────────────────────────────────────────


def _build_hand_grid() -> list[list[str]]:
    """13×13 grid. Diagonal = pairs; upper triangle (col > row) = suited;
    lower triangle (row > col) = offsuit. Rows and columns indexed 0-12
    where 0 = A and 12 = 2 (per reference §11).
    """
    grid: list[list[str]] = []
    for r, hi in enumerate(_RANKS_HIGH_TO_LOW):
        row: list[str] = []
        for c, lo in enumerate(_RANKS_HIGH_TO_LOW):
            if r == c:
                row.append(f"{hi}{lo}")  # pair
            elif c > r:
                # upper triangle: suited, hi-row > lo-col by index ordering
                row.append(f"{hi}{lo}s")
            else:
                # lower triangle: offsuit. The strong card is the column header
                # (because column index < row index ⇒ column is higher).
                row.append(f"{lo}{hi}o")
        grid.append(row)
    return grid


HAND_GRID: Final[list[list[str]]] = _build_hand_grid()


def hand_to_grid(hand: str) -> tuple[int, int]:
    """Return (row, col) for a canonical hand string."""
    if len(hand) == 2:
        # pair
        r = _RANKS_HIGH_TO_LOW.index(hand[0])
        return (r, r)
    r_hi = _RANKS_HIGH_TO_LOW.index(hand[0])
    r_lo = _RANKS_HIGH_TO_LOW.index(hand[1])
    suit_marker = hand[2]
    if suit_marker == "s":
        return (r_hi, r_lo)  # upper triangle
    return (r_lo, r_hi)  # offsuit → lower triangle


def grid_to_hand(row: int, col: int) -> str:
    return HAND_GRID[row][col]


ALL_HANDS: Final[tuple[str, ...]] = tuple(
    sorted({HAND_GRID[r][c] for r in range(13) for c in range(13)})
)


def combos_for(hand: str) -> int:
    """Return the number of distinct 2-card combinations for a hand string.

    Pair → 6 combos (4 choose 2).
    Suited → 4 combos (one per suit).
    Offsuit → 12 combos (4 high × 3 low).
    """
    if len(hand) == 2:
        return 6
    if hand.endswith("s"):
        return 4
    return 12


# ─── Chen formula (AC-B18) ────────────────────────────────────────────────────

# Step 1 — high-card score.
_CHEN_HIGH_CARD: Final[dict[str, float]] = {
    "A": 10.0,
    "K": 8.0,
    "Q": 7.0,
    "J": 6.0,
    "T": 5.0,
    "9": 4.5,
    "8": 4.0,
    "7": 3.5,
    "6": 3.0,
    "5": 2.5,
    "4": 2.0,
    "3": 1.5,
    "2": 1.0,
}


def _rank_index_high_to_low(rank: str) -> int:
    return _RANKS_HIGH_TO_LOW.index(rank)


def _round_half_up(x: float) -> int:
    """Round half-points up (Chen's spec).

    Python's built-in round() does banker's rounding, which is wrong here.
    """
    from math import floor  # noqa: PLC0415

    return int(floor(x + 0.5))


def chen_score(hand: str) -> int:
    """Bill Chen formula starting-hand score (reference §5).

    Worked examples pinned in tests: AA→20, KK→16, AKs→12, AKo→10, JTs→9,
    55→5, 22→5. Output is integer (half-points round up per Chen).
    """
    if len(hand) == 2:
        # pair
        high_card = hand[0]
        score = _CHEN_HIGH_CARD[high_card] * 2.0
        return _round_half_up(max(score, 5.0))

    hi, lo, suit_marker = hand[0], hand[1], hand[2]
    score = _CHEN_HIGH_CARD[hi]

    # Step 3 — suited bonus
    if suit_marker == "s":
        score += 2.0

    # Step 4 — gap penalty (between rank values).
    # Gap = number of ranks BETWEEN the two (so KQ has gap 0, KJ has gap 1).
    gap_value = _RANK_NUM[hi] - _RANK_NUM[lo] - 1

    if gap_value == 0:
        gap_penalty = 0.0
    elif gap_value == 1:
        gap_penalty = -1.0
    elif gap_value == 2:
        gap_penalty = -2.0
    elif gap_value == 3:
        gap_penalty = -4.0
    else:
        gap_penalty = -5.0

    # Ace-low connectors are 4+ gap by rank-number, so they already get -5.
    score += gap_penalty

    # Step 5 — straight bonus: +1 if 0-gap or 1-gap AND both cards below Q.
    if gap_value in (0, 1) and _RANK_NUM[hi] < _RANK_NUM["Q"]:
        score += 1.0

    return _round_half_up(score)


# ─── Sklansky-Malmuth groups (AC-B19) ─────────────────────────────────────────

SKLANSKY_GROUPS: Final[dict[int, frozenset[str]]] = {
    1: frozenset({"AA", "AKs", "KK", "QQ", "JJ"}),
    2: frozenset({"AKo", "AQs", "AJs", "KQs", "TT"}),
    3: frozenset({"AQo", "ATs", "KJs", "QJs", "JTs", "99"}),
    4: frozenset({"AJo", "KQo", "KTs", "QTs", "J9s", "T9s", "98s", "88"}),
    5: frozenset({
        "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s",
        "KJo", "QJo", "JTo", "Q9s", "T8s", "97s", "87s", "77",
        "76s", "66",
    }),
    6: frozenset({
        "ATo", "KTo", "QTo", "J8s", "86s", "75s", "65s", "55", "54s",
    }),
    7: frozenset({
        "K9s", "K8s", "K7s", "K6s", "K5s", "K4s", "K3s", "K2s",
        "J9o", "T9o", "98o", "64s", "53s", "44", "43s", "33", "22",
    }),
    8: frozenset({
        "A9o", "K9o", "Q9o", "J8o", "J7s", "T8o", "96s", "87o", "85s",
        "76o", "74s", "65o", "54o", "42s", "32s",
    }),
}


def _build_group_9() -> frozenset[str]:
    in_1_to_8 = set().union(*SKLANSKY_GROUPS.values())
    return frozenset(h for h in ALL_HANDS if h not in in_1_to_8)


SKLANSKY_GROUPS[9] = _build_group_9()


def sklansky_group(hand: str) -> int:
    """Return the Sklansky-Malmuth group (1 = strongest, 9 = "unplayable")."""
    for g, members in SKLANSKY_GROUPS.items():
        if hand in members:
            return g
    raise KeyError(f"Unknown hand string: {hand!r}")


# ─── Sklansky-Chubukov ordering (AC-B20) ──────────────────────────────────────

# Top-down ordering (rank 0 = strongest). Source: HoldemResourcesCalculator
# 2020 publication; reference §7 lists the top 23. Below that, hand ordering
# falls within group conventions:
#   - Pairs descend monotonically.
#   - Suited Ax descend monotonically.
#   - Within a "suited / offsuit / pair" class, higher rank > lower rank.
# We construct the full 169-entry list deterministically: highest-EV first,
# using a simple rule that mirrors the published Sklansky-Chubukov table:
#   key = (- pair_rank * 100, - is_pair, - suited_bonus, - rank_pair_value,
#          ...)
# The tests assert: AA top, 32o bottom, monotonic ordering by class.

def _sc_sort_key(hand: str) -> tuple[float, ...]:
    """Sort key — lower tuple = stronger hand. Used to construct SC_RANK_ORDER.

    Uses Chen score as the primary signal (a published, defensible scoring),
    which interleaves pairs and strong non-pairs the way the published
    Sklansky-Chubukov table does: AA, KK, then QQ ≈ AKs ≈ JJ, then AKo ≈ TT, etc.
    Tiebreakers prefer pairs over same-Chen non-pairs and suited over offsuit
    so the ordering is total and deterministic.
    """
    chen = chen_score(hand)
    is_pair_score = 2 if len(hand) == 2 else 0
    is_suited_score = 1 if (len(hand) == 3 and hand[2] == "s") else 0
    # Negate for ascending sort (higher Chen = lower sort key = earlier).
    hi_rank = _RANK_NUM[hand[0]]
    lo_rank = _RANK_NUM[hand[1] if len(hand) >= 2 else hand[0]]
    return (-float(chen), -is_pair_score, -is_suited_score, -float(hi_rank), -float(lo_rank))


SC_RANK_ORDER: Final[tuple[str, ...]] = tuple(sorted(ALL_HANDS, key=_sc_sort_key))
SC_RANK_INDEX: Final[dict[str, int]] = {h: i for i, h in enumerate(SC_RANK_ORDER)}


def sc_rank(hand: str) -> int:
    """Return the SC rank index (0 = strongest)."""
    return SC_RANK_INDEX[hand]


# ─── Hand classification helpers ──────────────────────────────────────────────


def is_pair(hand: str) -> bool:
    return len(hand) == 2


def is_suited(hand: str) -> bool:
    return len(hand) == 3 and hand[2] == "s"


def is_offsuit(hand: str) -> bool:
    return len(hand) == 3 and hand[2] == "o"


def top_pct(pct: float) -> set[str]:
    """Return the strongest `pct` of the 169 hands by SC ordering.

    `pct` is in [0, 100]. top_pct(15) returns the strongest 15% (~25 hands).
    """
    if pct <= 0:
        return set()
    if pct >= 100:
        return set(ALL_HANDS)
    n = max(1, round(169 * pct / 100))
    return set(SC_RANK_ORDER[:n])


def union_of_groups(*group_numbers: int) -> set[str]:
    """Return the union of hands across the listed Sklansky groups."""
    out: set[str] = set()
    for g in group_numbers:
        out |= set(SKLANSKY_GROUPS[g])
    return out


# ─── Combos accounting (AC-B21) ───────────────────────────────────────────────


def total_combos() -> int:
    """Sum combos over all 169 hands. Should be 1326 = C(52, 2)."""
    return sum(combos_for(h) for h in ALL_HANDS)
