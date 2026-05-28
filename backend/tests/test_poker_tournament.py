"""
test_poker_tournament.py — tournament glue tests.

Covers default blind schedule, payout structures, level advancement, button
rotation, and position labeling.
"""
from __future__ import annotations

import pytest

from backend.game.poker.tournament import (
    BLIND_SCHEDULE_DEFAULT,
    PAYOUT_STRUCTURE_BY_SEATS,
    current_level,
    effective_bb,
    next_button,
    payout_chips,
    payout_pcts_for_seats,
    seat_position_label,
)


# ─── Blind schedule ──────────────────────────────────────────────────────────


def test_default_schedule_starts_at_10_20_no_ante() -> None:
    assert BLIND_SCHEDULE_DEFAULT[0] == (10, 20, 0)


def test_antes_start_at_level_4() -> None:
    assert BLIND_SCHEDULE_DEFAULT[3][2] > 0


def test_blinds_monotonically_increase() -> None:
    for prev, curr in zip(BLIND_SCHEDULE_DEFAULT, BLIND_SCHEDULE_DEFAULT[1:], strict=False):
        assert curr[1] >= prev[1]


def test_current_level_first_hand_is_level_1() -> None:
    assert current_level(1) == (10, 20, 0)
    assert current_level(10) == (10, 20, 0)


def test_current_level_advances_at_hand_per_level_plus_1() -> None:
    assert current_level(11) == (15, 30, 0)
    assert current_level(31) == (50, 100, 10)


def test_current_level_caps_at_last() -> None:
    last = BLIND_SCHEDULE_DEFAULT[-1]
    assert current_level(10_000) == last


def test_current_level_invalid_raises() -> None:
    with pytest.raises(ValueError):
        current_level(0)


def test_effective_bb_simple() -> None:
    assert effective_bb(1000, 20) == 50.0


# ─── Payouts ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("seats", list(PAYOUT_STRUCTURE_BY_SEATS.keys()))
def test_payout_percentages_sum_to_100(seats: int) -> None:
    pcts = PAYOUT_STRUCTURE_BY_SEATS[seats]
    assert sum(pcts) == pytest.approx(100.0, abs=0.001)


def test_payout_chips_distributes_prize_pool() -> None:
    # 8 seats, 10000 cents prize pool
    payouts = payout_chips(10000, 8)
    assert sum(payouts) == 10000
    assert payouts[0] == 5000  # 50%
    assert payouts[1] == 3000  # 30%
    assert payouts[2] == 2000  # 20%


def test_payout_chips_handles_rounding() -> None:
    payouts = payout_chips(101, 3)  # 70%, 30%
    assert sum(payouts) == 101
    # 70% of 101 = 70.7 → 70; 30% = 30.3 → 30; remainder = 1 → goes to 1st.
    assert payouts[0] == 71


def test_payout_pcts_falls_back_for_unknown_seat_count() -> None:
    # 1 seat doesn't exist — function should return something sane.
    result = payout_pcts_for_seats(1)
    assert isinstance(result, list)
    assert sum(result) == pytest.approx(100.0)


# ─── Button rotation ─────────────────────────────────────────────────────────


def test_next_button_simple_3_handed() -> None:
    assert next_button(0, [0, 1, 2]) == 1
    assert next_button(1, [0, 1, 2]) == 2
    assert next_button(2, [0, 1, 2]) == 0


def test_next_button_skips_busted_seat() -> None:
    # Seat 1 busted; live seats are 0 and 2. Button on 0 should go to 2.
    assert next_button(0, [0, 2]) == 2


def test_next_button_no_live_seats_raises() -> None:
    with pytest.raises(ValueError):
        next_button(0, [])


# ─── Position labels ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("seats", [2, 3, 4, 5, 6, 7, 8, 9])
def test_button_seat_label_is_btn(seats: int) -> None:
    label = seat_position_label(0, button=0, seats=seats)
    assert label == "BTN"


def test_hu_labels() -> None:
    assert seat_position_label(0, button=0, seats=2) == "BTN"
    assert seat_position_label(1, button=0, seats=2) == "BB"


def test_three_handed_labels() -> None:
    assert seat_position_label(0, button=0, seats=3) == "BTN"
    assert seat_position_label(1, button=0, seats=3) == "SB"
    assert seat_position_label(2, button=0, seats=3) == "BB"


def test_9_max_labels_present() -> None:
    # Walk all seats from button=0 in a 9-handed game; expect set of canonical labels.
    labels = {seat_position_label(i, button=0, seats=9) for i in range(9)}
    expected = {"BTN", "SB", "BB", "UTG", "UTG1", "UTG2", "MP", "HJ", "CO"}
    assert labels == expected


def test_invalid_seat_count_raises() -> None:
    with pytest.raises(ValueError):
        seat_position_label(0, button=0, seats=10)
    with pytest.raises(ValueError):
        seat_position_label(0, button=0, seats=1)
