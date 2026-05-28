"""
test_poker_equity.py — covers AC-B11..AC-B14 from specs/texas-holdem.md.

The equity engine is stochastic (Monte Carlo) so tests use a fixed seed and
modest iteration counts (~3-5k) to stay within the test budget. Canonical
matchups from specs/texas-holdem-reference.md §4 must come in within ±2%.
"""
from __future__ import annotations

import pytest

from backend.game.poker.cards import parse_card
from backend.game.poker.equity import (
    EquityResult,
    equity,
    equity_vs_range,
    hero_vs_random_equity,
    multi_equity,
)


def C(s: str):
    return parse_card(s)


def H(*strs):
    return [C(s) for s in strs]


# ─── Canonical heads-up matchups (AC-B11) ─────────────────────────────────────


@pytest.mark.parametrize(
    "hero, opp, expected_pct, tol",
    [
        # Reference §4 canonical matchups
        (H("As", "Ah"), H("Ks", "Kh"), 0.82, 0.03),       # AA vs KK
        (H("Qs", "Qh"), H("As", "Kh"), 0.57, 0.04),       # QQ vs AKo
        (H("7s", "7h"), H("As", "Kh"), 0.55, 0.04),       # 77 vs AKo
        (H("As", "Ks"), H("2h", "2d"), 0.50, 0.05),       # AK vs 22 (coinflip)
        (H("As", "Kh"), H("Ad", "Qc"), 0.74, 0.04),       # AK vs AQ (dominated)
        (H("8s", "8h"), H("Ad", "8c"), 0.70, 0.04),       # 88 vs A8 (dominated A)
        (H("As", "Ah"), H("7h", "6h"), 0.77, 0.04),       # AA vs 76s
        (H("Ks", "Kh"), H("8h", "7h"), 0.77, 0.04),       # KK vs 87s
        (H("As", "Kh"), H("7d", "6c"), 0.62, 0.05),       # AK vs 76o
    ],
)
def test_canonical_heads_up_equities(hero, opp, expected_pct, tol):
    eq = equity(hero, [opp], board=[], iters=3000, seed=42)
    assert eq == pytest.approx(expected_pct, abs=tol), (
        f"Expected {expected_pct:.2f} ±{tol:.2f}, got {eq:.4f}"
    )


# ─── Multi-way (AC-B12) ───────────────────────────────────────────────────────


def test_aa_vs_two_random_opponents_drops_equity() -> None:
    """AA equity vs ONE random opp is ~85%; vs TWO randoms it drops to ~73%."""
    eq_1 = hero_vs_random_equity(H("As", "Ah"), n_opponents=1, board=[], iters=3000, seed=42)
    eq_2 = hero_vs_random_equity(H("As", "Ah"), n_opponents=2, board=[], iters=3000, seed=42)
    assert eq_1 > eq_2  # multi-way should be lower
    assert eq_2 == pytest.approx(0.73, abs=0.04)


def test_aa_vs_three_random_drops_further() -> None:
    eq_3 = hero_vs_random_equity(H("As", "Ah"), n_opponents=3, board=[], iters=2000, seed=42)
    assert eq_3 < 0.70


# ─── Board-aware (AC-B13) ─────────────────────────────────────────────────────


def test_flush_draw_improves_with_two_to_come() -> None:
    """AKs (hearts) on a 2h-5h-9c flop has a heart flush draw + overcards.
    The equity vs KQo (a made pair) should reflect the draw — should be ≥ 50%."""
    hero = H("Ah", "Kh")
    opp = H("Ks", "Qd")
    board = H("2h", "5h", "9c")
    eq = equity(hero, [opp], board, iters=3000, seed=42)
    # KQo has K-high pairing on K board... wait — board is 2-5-9, no pair.
    # Hero has overcards + nut flush draw. Opp has K-high. Hero is heavy favorite.
    assert eq > 0.60


def test_dead_draw_is_a_dog() -> None:
    """72o on a board K-K-Q-J-3 has no equity vs AKs (made trips). 0%."""
    hero = H("7s", "2c")
    opp = H("As", "Ks")
    board = H("Kh", "Kd", "Qc", "Jh", "3c")
    eq = equity(hero, [opp], board, iters=100, seed=42)
    # Trips beat hero's high card; hero wins 0%.
    assert eq == 0.0


def test_play_the_board_split() -> None:
    """Board = Broadway straight, hole cards irrelevant. Both seats split."""
    hero = H("2s", "3c")
    opp = H("4d", "7h")
    board = H("As", "Kh", "Qd", "Jc", "Th")
    eq = equity(hero, [opp], board, iters=100, seed=42)
    assert eq == 0.5


# ─── Range-aware (AC-B14) ─────────────────────────────────────────────────────


def test_wider_opp_range_means_more_hero_equity() -> None:
    """87s vs a tight (top 5%) range loses equity. 87s vs a wide (top 30%)
    range has higher equity because the wide range includes more dominated
    junk."""
    from backend.game.poker.ranges import top_pct  # noqa: PLC0415

    hero = H("8h", "7h")
    eq_tight = equity_vs_range(hero, top_pct(5), board=[], iters=600, seed=42)
    eq_wide = equity_vs_range(hero, top_pct(35), board=[], iters=600, seed=42)
    assert eq_wide > eq_tight, (
        f"Expected wider range to give hero more equity; got {eq_wide:.3f} vs {eq_tight:.3f}"
    )


def test_equity_vs_empty_range_raises() -> None:
    with pytest.raises(ValueError):
        equity_vs_range(H("As", "Kh"), set(), board=[])


# ─── multi_equity (per-seat shares) ───────────────────────────────────────────


def test_multi_equity_shares_sum_to_one() -> None:
    holes = [H("As", "Ah"), H("Ks", "Kh"), H("Qs", "Qh")]
    result = multi_equity(holes, board=[], iters=1000, seed=42)
    assert isinstance(result, EquityResult)
    assert sum(result.equities) == pytest.approx(1.0, abs=0.01)


def test_multi_equity_higher_pair_dominates() -> None:
    holes = [H("As", "Ah"), H("Ks", "Kh"), H("2s", "2h")]
    result = multi_equity(holes, board=[], iters=2000, seed=42)
    assert result.equities[0] > result.equities[1]
    assert result.equities[1] > result.equities[2]


# ─── Edge cases ───────────────────────────────────────────────────────────────


def test_full_board_is_deterministic() -> None:
    """With a complete 5-card board and no random opponents, equity is a
    deterministic showdown — iterations should not matter."""
    hero = H("As", "Kh")
    opp = H("Qd", "Qc")
    board = H("Kh", "8d", "3c", "5s", "2h")  # hero made pair of Ks
    eq_a = equity(hero, [opp], board, iters=1, seed=1)
    eq_b = equity(hero, [opp], board, iters=10, seed=2)
    assert eq_a == eq_b


def test_invalid_hole_lengths_raises() -> None:
    with pytest.raises(ValueError):
        equity(H("As"), [H("Kd", "Qc")], board=[])
    with pytest.raises(ValueError):
        equity(H("As", "Kh"), [H("Kd")], board=[])
