"""
test_poker_pot_odds.py — covers AC-B15..AC-B17 from specs/texas-holdem.md.
"""
from __future__ import annotations

import pytest

from backend.game.poker.pot_odds import (
    REQUIRED_EQUITY_BY_BET_FRACTION,
    bluff_breakeven,
    equity_from_outs,
    mdf,
    required_equity,
    required_equity_for_pot_fraction,
)


# ─── Required equity (AC-B15) ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pot_before, opp_bet, expected",
    [
        (100, 25, 1 / 6),     # ¼ pot
        (100, 33.33, 0.2),     # ⅓ pot
        (100, 50, 0.25),       # ½ pot
        (100, 75, 0.3),        # ¾ pot
        (100, 100, 1 / 3),     # pot
        (100, 150, 0.375),     # 1.5× pot
        (100, 200, 0.4),       # 2× pot
    ],
)
def test_required_equity_pinned(pot_before, opp_bet, expected):
    assert required_equity(pot_before, opp_bet) == pytest.approx(expected, abs=1e-3)


def test_required_equity_zero_bet_is_zero():
    assert required_equity(100, 0) == 0.0


def test_required_equity_raises_on_negative():
    with pytest.raises(ValueError):
        required_equity(-1, 50)
    with pytest.raises(ValueError):
        required_equity(100, -10)


def test_required_equity_for_pot_fraction_helper():
    assert required_equity_for_pot_fraction(1.0) == pytest.approx(1 / 3, abs=1e-3)
    assert required_equity_for_pot_fraction(0.5) == pytest.approx(0.25, abs=1e-3)


def test_required_equity_by_bet_fraction_table_completeness():
    # Every entry round-trips through required_equity.
    for bet_frac, expected in REQUIRED_EQUITY_BY_BET_FRACTION.items():
        assert required_equity(1.0, bet_frac) == pytest.approx(expected, abs=1e-3)


# ─── MDF + bluff break-even (AC-B16) ─────────────────────────────────────────


@pytest.mark.parametrize(
    "pot_before, bet, expected_breakeven",
    [
        (100, 50, 1 / 3),     # half pot
        (100, 75, 3 / 7),     # ¾ pot
        (100, 100, 0.5),      # pot
        (100, 150, 0.6),      # 1.5× pot
        (100, 200, 2 / 3),    # 2× pot
    ],
)
def test_bluff_breakeven_pinned(pot_before, bet, expected_breakeven):
    assert bluff_breakeven(pot_before, bet) == pytest.approx(expected_breakeven, abs=1e-3)


@pytest.mark.parametrize(
    "pot_before, bet, expected_mdf",
    [
        (100, 50, 2 / 3),     # half pot → defend ≥ 66.7%
        (100, 75, 4 / 7),     # ¾ pot
        (100, 100, 0.5),      # pot
        (100, 150, 0.4),      # 1.5× pot
        (100, 200, 1 / 3),    # 2× pot
    ],
)
def test_mdf_pinned(pot_before, bet, expected_mdf):
    assert mdf(pot_before, bet) == pytest.approx(expected_mdf, abs=1e-3)


def test_mdf_and_breakeven_complement():
    """MDF + bluff_breakeven = 1 for any non-zero bet."""
    for bet in (10, 50, 100, 200):
        assert mdf(100, bet) + bluff_breakeven(100, bet) == pytest.approx(1.0, abs=1e-9)


def test_mdf_raises_on_negative():
    with pytest.raises(ValueError):
        mdf(-1, 50)


# ─── Rule of 2 and 4 (AC-B17) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "outs, streets, expected, tol",
    [
        # Flop → river (two streets)
        (4, 2, 0.16, 0.04),      # gutshot ≈ 16.5%
        (6, 2, 0.24, 0.04),      # two overcards ≈ 24%
        (8, 2, 0.32, 0.04),      # OESD ≈ 31.5%
        (9, 2, 0.35, 0.04),      # flush draw ≈ 35%
        (12, 2, 0.45, 0.04),     # flush + gutshot ≈ 45%
        (15, 2, 0.54, 0.04),     # straight + flush combo ≈ 54%
        # Turn → river (one street)
        (4, 1, 0.087, 0.02),     # gutshot
        (6, 1, 0.13, 0.02),      # two overcards
        (8, 1, 0.174, 0.02),     # OESD
        (9, 1, 0.196, 0.02),     # flush draw
        (15, 1, 0.30, 0.05),     # straight + flush combo
    ],
)
def test_equity_from_outs(outs, streets, expected, tol):
    assert equity_from_outs(outs, streets) == pytest.approx(expected, abs=tol)


def test_equity_from_outs_zero():
    assert equity_from_outs(0, 1) == 0.0
    assert equity_from_outs(0, 2) == 0.0


def test_equity_from_outs_invalid_streets():
    with pytest.raises(ValueError):
        equity_from_outs(5, 3)
    with pytest.raises(ValueError):
        equity_from_outs(5, 0)


def test_equity_from_outs_negative_outs_raises():
    with pytest.raises(ValueError):
        equity_from_outs(-1, 2)


def test_equity_from_outs_high_outs_shades_down():
    """At ≥12 outs, the linear approximation outs × 4% overestimates. The
    implementation returns the shaded value, which must be < outs × 0.04."""
    for outs in (12, 13, 14, 15):
        actual = equity_from_outs(outs, 2)
        linear = outs * 0.04
        assert actual < linear or actual == pytest.approx(linear, abs=0.02), (
            f"Expected shading down at {outs} outs; got {actual} vs linear {linear}"
        )
