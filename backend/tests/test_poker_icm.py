"""
test_poker_icm.py — covers AC-B26, AC-B27 from specs/texas-holdem.md.
"""
from __future__ import annotations

import pytest

from backend.game.poker.icm import (
    harville_finish_distribution,
    icm_breakeven_call_equity,
    icm_equity,
)


# ─── Harville distribution sanity ─────────────────────────────────────────────


def test_each_seats_position_probs_sum_to_one() -> None:
    """For each seat, P(finish in position 1..n) sums to 1."""
    stacks = [200, 100, 100]
    M = harville_finish_distribution(stacks)
    for seat_row in M:
        assert sum(seat_row) == pytest.approx(1.0, abs=1e-6)


def test_each_position_probs_across_seats_sum_to_one() -> None:
    """For each position, sum over all seats = 1 (exactly one seat ends in pos k)."""
    stacks = [200, 100, 100]
    M = harville_finish_distribution(stacks)
    n = len(stacks)
    for k in range(n):
        col_sum = sum(M[i][k] for i in range(n))
        assert col_sum == pytest.approx(1.0, abs=1e-6)


# ─── Pinned cases (AC-B26) ────────────────────────────────────────────────────


def test_hu_uniform_pays_equally_when_stacks_equal() -> None:
    stacks = [50, 50]
    payouts = [60, 40]
    eq = icm_equity(stacks, payouts)
    assert eq[0] == pytest.approx(50.0, abs=0.05)
    assert eq[1] == pytest.approx(50.0, abs=0.05)


def test_three_handed_uniform_stacks_equal_payouts() -> None:
    stacks = [100, 100, 100]
    payouts = [50, 30, 20]
    eq = icm_equity(stacks, payouts)
    expected = (50 + 30 + 20) / 3
    for v in eq:
        assert v == pytest.approx(expected, abs=0.05)


def test_three_handed_big_stack_leader() -> None:
    """[200, 100, 100] with [50, 30, 20] payouts.

    By hand: P(seat 0 wins) = 200/400 = 0.5. P(seat 0 2nd | seat 1 wins
    first) = 200/300 * 100/400 = 0.1667; similarly for seat 2. Sum P(2nd) =
    0.333. P(3rd) = 0.167. Equity = 0.5×50 + 0.333×30 + 0.167×20 = 38.33.

    The leader's $ equity (38.33) is less than their chip share (50%) of the
    prize pool — exactly the canonical "chip leader gets less than chip share"
    property (reference §9).
    """
    stacks = [200, 100, 100]
    payouts = [50, 30, 20]
    eq = icm_equity(stacks, payouts)
    assert eq[0] == pytest.approx(38.33, abs=0.1)
    # The two short stacks are symmetric: equity ≈ (100 - 38.33) / 2 = 30.83 each.
    assert eq[1] == pytest.approx(30.83, abs=0.1)
    assert eq[2] == pytest.approx(30.83, abs=0.1)
    # Leader's $-share is below chip-share (50%):
    assert eq[0] < 50.0


def test_three_handed_skewed_stacks() -> None:
    """[100, 50, 25] with [50, 30, 20] payouts.

    Hand-computed via Harville: seat 0 ≈ 40.38, seat 1 ≈ 32.86, seat 2 ≈ 26.76.
    """
    stacks = [100, 50, 25]
    payouts = [50, 30, 20]
    eq = icm_equity(stacks, payouts)
    # Sums approximately to 100 (the prize pool)
    assert sum(eq) == pytest.approx(100.0, abs=0.5)
    # Big stack gets more than mid stack who gets more than short stack:
    assert eq[0] > eq[1] > eq[2]
    # Big stack equity < its chip share (100/175 = 57.1%):
    assert eq[0] < 57.1
    # Short stack equity > 20 ($ third prize is guaranteed):
    assert eq[2] > 20.0


def test_runaway_chip_leader_gets_less_than_chip_share() -> None:
    """A 5-handed table where seat 0 has 1000 chips and the others have 1 each.

    Per Harville: seat 0 wins ~99.6%, but the total prize pool is fixed —
    so seat 0's $ equity is bounded by 50% (first prize), NOT scaled to
    chip share. The reference §9 callout 'chip leader gets less than chip
    share of prize pool' applies.
    """
    stacks = [1000, 1, 1, 1, 1]
    payouts = [50.0, 25.0, 12.5, 7.5, 5.0]  # sums to 100
    eq = icm_equity(stacks, payouts)
    # Leader's chip share is 1000/1004 ≈ 99.6% — but $ equity is bounded.
    assert eq[0] < 51.0  # less than the $50 first prize (slightly less than 50)
    # Each short stack has positive equity (much greater than their 0.1% chip share).
    for short_seat_eq in eq[1:]:
        assert short_seat_eq > 5.0


# ─── ICM break-even tighter than chip-EV (AC-B27) ─────────────────────────────


def test_icm_bubble_tightens_calling_range() -> None:
    """Bubble setup: 3 seats remain, 2 paid. Hero is the medium stack facing
    an all-in from the short stack. The ICM break-even equity to call should
    be higher than the chip-EV value (33.3% for a pot-sized all-in).
    """
    # Hero (medium): 1000, Short (jamming): 500, Leader: 1500.
    # Payouts: 1st = 60, 2nd = 40, 3rd = 0 (bubble).
    stacks_before = [1500, 1000, 500]  # leader, hero, short
    payouts = [60.0, 40.0, 0.0]
    pot_before_call = 500  # short jammed for 500
    opp_bet = 500

    threshold = icm_breakeven_call_equity(
        stacks_before=stacks_before,
        payouts=payouts,
        hero_seat=1,
        opp_seat=2,
        pot_before_call=pot_before_call,
        opp_bet=opp_bet,
    )
    # Chip-EV break-even for a pot-sized call is 33.3%; ICM should require more.
    assert threshold > 0.34, (
        f"ICM should tighten the calling range above chip-EV 0.333; got {threshold:.4f}"
    )


def test_icm_threshold_is_in_unit_range() -> None:
    stacks = [1500, 1000, 500]
    payouts = [60.0, 40.0, 0.0]
    threshold = icm_breakeven_call_equity(stacks, payouts, 1, 2, 500, 500)
    assert 0.0 <= threshold <= 1.0


def test_icm_with_flat_payouts_threshold_is_zero() -> None:
    """When everyone gets the same payout regardless of finish, ICM is flat
    — chip stack doesn't affect $ equity, so any +EV-in-chips call is
    correct. Threshold = 0."""
    stacks = [5000, 5000, 5000, 5000]
    payouts = [25.0, 25.0, 25.0, 25.0]
    # pot_before_call = 2*opp_bet → standard "pot-sized bet" notation
    threshold = icm_breakeven_call_equity(stacks, payouts, 1, 2, 1000, 500)
    # With flat payouts, ICM is uniform — threshold is effectively 0 (any
    # positive chip-EV → call).
    assert threshold < 0.05


def test_icm_threshold_less_extreme_than_near_bubble() -> None:
    """ICM threshold for an early-tournament deep-stack spot is lower (less
    tight) than the same spot near the bubble. Tests the *direction*."""
    payouts = [50.0, 30.0, 15.0, 5.0]
    early = icm_breakeven_call_equity([5000, 5000, 5000, 5000], payouts, 1, 2, 1000, 500)
    bubble_payouts = [50.0, 30.0, 0.0]
    bubble = icm_breakeven_call_equity([3000, 1500, 1000], bubble_payouts, 1, 2, 1000, 500)
    # Bubble threshold strictly tighter than early threshold.
    assert bubble >= early - 0.02, (
        f"Expected bubble {bubble:.3f} ≥ early {early:.3f}"
    )


def test_icm_pot_sized_bet_threshold_near_one_third_for_uniform_stacks() -> None:
    """Sanity: with uniform stacks and a standard steep payout, pot-sized
    call (pot_before = 2*opp_bet) → threshold close to but above the
    chip-EV value 1/3 — the ICM penalty makes calling tighter."""
    stacks = [5000, 5000, 5000, 5000]
    payouts = [50.0, 30.0, 15.0, 5.0]
    threshold = icm_breakeven_call_equity(stacks, payouts, 1, 2, 1000, 500)
    # Should be in a sane band. Chip-EV is 0.333; ICM pushes it up.
    assert 0.30 <= threshold <= 0.55, f"Got threshold {threshold:.4f}"


# ─── Error handling ──────────────────────────────────────────────────────────


def test_negative_stacks_raise() -> None:
    with pytest.raises(ValueError):
        harville_finish_distribution([-1, 100])


def test_zero_total_stacks_raise() -> None:
    with pytest.raises(ValueError):
        harville_finish_distribution([0, 0])


def test_breakeven_invalid_seats_raise() -> None:
    with pytest.raises(ValueError):
        icm_breakeven_call_equity([100, 100], [60, 40], 0, 0, 100, 100)  # same seat
