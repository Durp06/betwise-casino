"""
test_poker_ranges.py — covers AC-B18..AC-B21 from specs/texas-holdem.md.

Pins Chen formula worked examples (reference §5), Sklansky-Malmuth group
completeness (reference §6), 169-hand grid (reference §11), and Sklansky-
Chubukov ordering invariants (reference §7).
"""
from __future__ import annotations

import pytest

from backend.game.poker import ranges
from backend.game.poker.ranges import (
    ALL_HANDS,
    HAND_GRID,
    SC_RANK_ORDER,
    SKLANSKY_GROUPS,
    chen_score,
    combos_for,
    grid_to_hand,
    hand_str,
    hand_to_grid,
    is_offsuit,
    is_pair,
    is_suited,
    sc_rank,
    sklansky_group,
    top_pct,
    total_combos,
    union_of_groups,
)


# ─── Chen formula (AC-B18) ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "hand, expected",
    [
        ("AA", 20),
        ("KK", 16),
        ("QQ", 14),
        ("JJ", 12),
        ("TT", 10),
        ("99", 9),
        ("88", 8),
        ("77", 7),
        ("66", 6),
        ("55", 5),
        ("44", 5),  # minimum 5
        ("33", 5),
        ("22", 5),
        ("AKs", 12),
        ("AKo", 10),
        ("JTs", 9),
        ("T9s", 8),  # 5 + 2 (suited) + 1 (straight bonus, both below Q, 0-gap)
    ],
)
def test_chen_worked_examples(hand: str, expected: int) -> None:
    assert chen_score(hand) == expected


def test_chen_pair_always_at_least_5() -> None:
    for pair in ("22", "33", "44", "55"):
        assert chen_score(pair) == 5


def test_chen_suited_better_than_offsuit() -> None:
    for hand in ("AK", "AQ", "KQ", "JT", "T9", "98"):
        s = chen_score(f"{hand}s")
        o = chen_score(f"{hand}o")
        assert s > o, f"Expected {hand}s > {hand}o (suited bonus)"


def test_chen_gap_penalty_increases_with_gap() -> None:
    # 0-gap KQs scores higher than 4-gap K7s for the same high card.
    assert chen_score("KQs") > chen_score("K7s")


# ─── Sklansky-Malmuth groups (AC-B19) ─────────────────────────────────────────


def test_groups_1_to_9_total_169_hands() -> None:
    total: set[str] = set()
    for members in SKLANSKY_GROUPS.values():
        total |= members
    assert len(total) == 169


def test_groups_are_disjoint() -> None:
    # Every hand belongs to exactly one group.
    seen: dict[str, int] = {}
    for g, members in SKLANSKY_GROUPS.items():
        for h in members:
            assert h not in seen, f"{h} in groups {seen[h]} and {g}"
            seen[h] = g
    assert len(seen) == 169


def test_group_1_premium_set() -> None:
    expected = {"AA", "KK", "QQ", "JJ", "AKs"}
    assert SKLANSKY_GROUPS[1] == expected


def test_group_9_is_everything_outside_1_to_8() -> None:
    in_1_to_8 = set().union(*[SKLANSKY_GROUPS[g] for g in range(1, 9)])
    assert SKLANSKY_GROUPS[9] == (set(ALL_HANDS) - in_1_to_8)


def test_sklansky_group_lookup() -> None:
    assert sklansky_group("AA") == 1
    assert sklansky_group("AKs") == 1
    assert sklansky_group("AKo") == 2
    assert sklansky_group("72o") == 9  # the canonical "worst" hand


def test_union_of_groups() -> None:
    g12 = union_of_groups(1, 2)
    assert "AA" in g12
    assert "AKo" in g12
    assert "55" not in g12  # 55 is group 6


# ─── 169-hand grid (AC-B21) ───────────────────────────────────────────────────


def test_hand_grid_has_13x13_dimension() -> None:
    assert len(HAND_GRID) == 13
    for row in HAND_GRID:
        assert len(row) == 13


def test_hand_grid_diagonal_is_pairs() -> None:
    for i in range(13):
        h = HAND_GRID[i][i]
        assert is_pair(h)


def test_hand_grid_upper_triangle_is_suited() -> None:
    for r in range(13):
        for c in range(r + 1, 13):
            assert is_suited(HAND_GRID[r][c]), f"Expected suited at ({r},{c}); got {HAND_GRID[r][c]}"


def test_hand_grid_lower_triangle_is_offsuit() -> None:
    for r in range(13):
        for c in range(r):
            assert is_offsuit(HAND_GRID[r][c]), f"Expected offsuit at ({r},{c}); got {HAND_GRID[r][c]}"


def test_hand_grid_169_distinct() -> None:
    flat = {h for row in HAND_GRID for h in row}
    assert len(flat) == 169


def test_hand_to_grid_roundtrip() -> None:
    for h in ALL_HANDS:
        r, c = hand_to_grid(h)
        assert grid_to_hand(r, c) == h


def test_combos_for() -> None:
    assert combos_for("AA") == 6
    assert combos_for("AKs") == 4
    assert combos_for("AKo") == 12


def test_total_combos_is_1326() -> None:
    """C(52, 2) = 1326."""
    assert total_combos() == 1326


def test_169_pairs_suited_offsuit_breakdown() -> None:
    pairs = [h for h in ALL_HANDS if is_pair(h)]
    suited = [h for h in ALL_HANDS if is_suited(h)]
    offsuit = [h for h in ALL_HANDS if is_offsuit(h)]
    assert len(pairs) == 13
    assert len(suited) == 78
    assert len(offsuit) == 78


# ─── SC ordering (AC-B20) ─────────────────────────────────────────────────────


def test_sc_rank_order_starts_with_AA() -> None:
    assert SC_RANK_ORDER[0] == "AA"


def test_sc_rank_order_ends_with_weak_offsuit() -> None:
    """The bottom of the SC ordering is some low-rank disconnected offsuit
    hand. The exact identity depends on the underlying scoring (published SC
    has 32o at #169; Chen-based ordering puts a non-connector like 72o or 82o
    at the bottom). What we pin: the bottom-5 are all offsuit, low-rank
    (high card ≤ 9), and not pairs."""
    bottom_5 = SC_RANK_ORDER[-5:]
    for h in bottom_5:
        assert len(h) == 3 and h[2] == "o", f"{h} should be offsuit"
        # High card ≤ 9 (the worst hands have low high cards).
        hi_num = {"A": 14, "K": 13, "Q": 12, "J": 11, "T": 10}.get(h[0], int(h[0]) if h[0].isdigit() else 0)
        assert hi_num <= 9, f"{h} has too high a high card to be in the bottom 5"


def test_sc_rank_order_has_169_entries() -> None:
    assert len(SC_RANK_ORDER) == 169


def test_sc_pairs_descend_monotonically() -> None:
    pair_ranks = [(p, sc_rank(p)) for p in ("AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66", "55", "44", "33", "22")]
    for (p1, r1), (p2, r2) in zip(pair_ranks, pair_ranks[1:], strict=False):
        assert r1 < r2, f"Expected {p1} stronger than {p2}, got ranks {r1} vs {r2}"


def test_sc_pairs_dominate_same_high_card_offsuit() -> None:
    # 22 (a pair) should be ranked strictly stronger than any J2o style hand
    # that pairs only the high card and runs a 2 kicker.
    assert sc_rank("22") < sc_rank("J2o")
    assert sc_rank("33") < sc_rank("Q3o")


def test_sc_aks_top10_class() -> None:
    """AKs should be in the top 10 ranks (strong premium)."""
    assert sc_rank("AKs") < 10


# ─── hand_str helper ──────────────────────────────────────────────────────────


def test_hand_str_pair() -> None:
    assert hand_str("7", "hearts", "7", "spades") == "77"


def test_hand_str_suited() -> None:
    assert hand_str("A", "hearts", "K", "hearts") == "AKs"
    assert hand_str("K", "hearts", "A", "hearts") == "AKs"  # order shouldn't matter


def test_hand_str_offsuit() -> None:
    assert hand_str("A", "hearts", "K", "spades") == "AKo"


def test_hand_str_handles_10_value() -> None:
    """Card wire format uses '10' but hand strings use 'T'."""
    assert hand_str("J", "hearts", "10", "hearts") == "JTs"
    assert hand_str("10", "hearts", "J", "hearts") == "JTs"


# ─── top_pct ──────────────────────────────────────────────────────────────────


def test_top_pct_returns_strongest_first() -> None:
    top10 = top_pct(10)
    assert "AA" in top10
    assert "KK" in top10
    # 32o definitely not in top 10%.
    assert "32o" not in top10


def test_top_pct_bounds() -> None:
    assert top_pct(0) == set()
    assert top_pct(100) == set(ALL_HANDS)


def test_top_pct_size_proportional() -> None:
    assert 12 <= len(top_pct(8)) <= 15  # ~13-14 hands for 8%
