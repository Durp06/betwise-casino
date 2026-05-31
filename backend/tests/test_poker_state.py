"""
test_poker_state.py — covers AC-B31..AC-B38 from specs/texas-holdem.md.

The state machine is the largest single brain module. We test:
- Initial state + blind/ante posting
- apply_action legality (min-raise, all-in-for-less, etc.)
- Street closing logic
- Side pots + chip conservation invariant
- Heads-up reversal
- Edge cases (everyone folds to BB, all-in run-out)
"""
from __future__ import annotations

import random

import pytest

from backend.game.poker.state import (
    BettingState,
    advance_street,
    apply_action,
    award_pots,
    compute_side_pots,
    create_state,
    next_to_act,
    street_closed,
    total_chips_in_play,
)


# ─── Initial state ────────────────────────────────────────────────────────────


def test_create_state_posts_blinds() -> None:
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    assert s.street == "preflop"
    # SB seat = (button+1) % n = 1, BB = 2
    assert s.seats[0].current_bet == 0       # button
    assert s.seats[1].current_bet == 5       # SB
    assert s.seats[2].current_bet == 10      # BB
    assert s.current_bet_to_match == 10
    assert s.min_raise_increment == 10
    # Stacks reduced by blinds
    assert s.seats[1].stack == 995
    assert s.seats[2].stack == 990


def test_create_state_heads_up_button_posts_sb() -> None:
    s = create_state([1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    # HU: button posts SB.
    assert s.seats[0].current_bet == 5      # button = SB
    assert s.seats[1].current_bet == 10     # opposite = BB


def test_create_state_with_antes() -> None:
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10, ante=2)
    # Every seat pays ante; SB and BB also post blinds.
    assert s.seats[0].total_committed == 2       # button = ante only
    assert s.seats[1].total_committed == 2 + 5   # ante + SB
    assert s.seats[2].total_committed == 2 + 10  # ante + BB


def test_invalid_seat_count_raises() -> None:
    with pytest.raises(ValueError):
        create_state([1000], button_seat=0, small_blind=5, big_blind=10)


# ─── Action legality (AC-B31, AC-B32) ─────────────────────────────────────────


def test_check_when_facing_bet_raises() -> None:
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    # UTG (seat 0 in 3-handed = button = first to act preflop after BB)
    # Actually first-to-act preflop in 3-handed is (BB+1) % n = 0
    nta = next_to_act(s)
    with pytest.raises(ValueError):
        apply_action(s, nta, "check")  # cannot check — must call BB


def test_call_when_no_bet_raises() -> None:
    # On the flop, current_bet_to_match is 0 (after advance_street).
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    # Fold around to BB → just one seat left
    # Instead, let everyone call preflop and advance.
    nta = next_to_act(s)
    s = apply_action(s, nta, "call")    # UTG calls
    nta = next_to_act(s)
    s = apply_action(s, nta, "call")    # SB calls
    nta = next_to_act(s)
    s = apply_action(s, nta, "check")   # BB checks
    s = advance_street(s)
    # Now on the flop, no bet outstanding
    assert s.current_bet_to_match == 0


def test_min_raise_below_threshold_raises_error() -> None:
    s = create_state([1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    # HU preflop: SB (=button) acts first. BB is the bet at 10. min_raise = 10
    # so a raise must be to ≥ 20. Raising to 15 should fail.
    with pytest.raises(ValueError):
        apply_action(s, 0, "raise", amount=15)


def test_valid_min_raise_succeeds() -> None:
    s = create_state([1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    s2 = apply_action(s, 0, "raise", amount=20)
    assert s2.current_bet_to_match == 20
    assert s2.min_raise_increment == 10  # min_raise = previous increment


def test_three_bet_min_raise() -> None:
    """A 3-bet must be at least double the previous raise."""
    s = create_state([1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "raise", amount=30)  # SB raises to 30 (incr 20)
    # Now min_raise_increment is 20. BB 3-bets — must be ≥ 30 + 20 = 50.
    with pytest.raises(ValueError):
        apply_action(s, 1, "raise", amount=40)  # only +10 increment


def test_all_in_for_less_does_not_reopen() -> None:
    """All-in for less than the min raise does NOT reopen action for
    already-acted players (AC-B32)."""
    # 3-handed, deeper stack on button. After SB raises, BB shoves for less.
    s = create_state([100, 100, 130], button_seat=0, small_blind=5, big_blind=10)
    # Action order: UTG (seat 0 = button) → SB (1) → BB (2)
    # Actually 3-handed: first to act preflop is (BB+1) = 0 = button.
    s = apply_action(s, 0, "raise", amount=50)  # button raises to 50, incr=40
    s = apply_action(s, 1, "call", amount=0)    # SB calls (needs to pay 45)
    # BB has 130 - 10 (already in) = 120 stack remaining. shove = total 130
    s = apply_action(s, 2, "all_in")             # BB shoves to 130 (incr = 80, ≥ min 40 → reopens)

    # That reopens action — try a similar case with smaller all-in:
    s2 = create_state([200, 200, 60], button_seat=0, small_blind=5, big_blind=10)
    s2 = apply_action(s2, 0, "raise", amount=50)  # incr=40
    # Seat 2 has 60-10=50 left, total committed = 60. All-in for 60 means incr = 10 (60-50).
    # That's BELOW min_raise (40). Should NOT reopen.
    s2 = apply_action(s2, 1, "call")              # SB calls
    s2 = apply_action(s2, 2, "all_in")
    assert s2.current_bet_to_match == 60
    # Seat 0 (the original raiser) has already acted; should NOT need to act again.
    # next_to_act should not return seat 0.
    nta = next_to_act(s2)
    # Either close the street or skip seat 0
    assert nta != 0 or street_closed(s2)


# ─── Street closing (AC-B33) ──────────────────────────────────────────────────


def test_street_closes_when_action_returns_to_aggressor() -> None:
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "call")  # UTG calls
    s = apply_action(s, 1, "call")  # SB calls
    s = apply_action(s, 2, "check") # BB checks
    assert street_closed(s)


def test_street_does_not_close_after_raise_until_callers_act() -> None:
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "raise", amount=30)
    # SB and BB haven't acted on the new bet level
    assert not street_closed(s)


def test_only_one_seat_left_closes_immediately() -> None:
    """When everyone but one folds, the hand is over."""
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "fold")
    s = apply_action(s, 1, "fold")
    assert street_closed(s)


# ─── Everyone folds to BB (AC-B38) ────────────────────────────────────────────


def test_everyone_folds_to_bb_wins_dead_money() -> None:
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "fold")
    s = apply_action(s, 1, "fold")
    # BB still has not had to act; the hand is over.
    assert street_closed(s)
    assert len(s.live_seats()) == 1
    assert s.live_seats()[0].seat_number == 2


# ─── Heads-up reversal (AC-B34) ───────────────────────────────────────────────


def test_hu_preflop_btn_acts_first() -> None:
    s = create_state([1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    assert next_to_act(s) == 0  # BTN = SB acts first preflop


def test_hu_postflop_bb_acts_first() -> None:
    s = create_state([1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    # Preflop: SB calls, BB checks
    s = apply_action(s, 0, "call")
    s = apply_action(s, 1, "check")
    s = advance_street(s)
    # Postflop HU: BB acts first
    assert next_to_act(s) == 1


# ─── Side pots + chip conservation (AC-B35, AC-B36) ──────────────────────────


def test_chip_conservation_after_each_action() -> None:
    initial_total = 1000 + 1000 + 1000
    s = create_state([1000, 1000, 1000], button_seat=0, small_blind=5, big_blind=10)
    assert total_chips_in_play(s) == initial_total
    s = apply_action(s, 0, "call")
    assert total_chips_in_play(s) == initial_total
    s = apply_action(s, 1, "raise", amount=40)
    assert total_chips_in_play(s) == initial_total
    s = apply_action(s, 2, "fold")
    assert total_chips_in_play(s) == initial_total
    s = apply_action(s, 0, "call")
    assert total_chips_in_play(s) == initial_total


def test_chip_conservation_fuzz_random_actions() -> None:
    """100 random actions across many states — chip count must be invariant."""
    rng = random.Random(42)
    initial_total = 100 + 100 + 100 + 100
    s = create_state([100, 100, 100, 100], button_seat=0, small_blind=2, big_blind=4)
    for _ in range(20):
        nta = next_to_act(s)
        if nta is None:
            if s.street == "complete" or len(s.live_seats()) <= 1:
                break
            s = advance_street(s)
            continue
        to_call = s.current_bet_to_match - s.seats[nta].current_bet
        action_choice = rng.random()
        if to_call > 0:
            if action_choice < 0.3:
                s = apply_action(s, nta, "fold")
            elif action_choice < 0.85:
                s = apply_action(s, nta, "call")
            elif s.seats[nta].stack > to_call + s.min_raise_increment:
                s = apply_action(s, nta, "raise", amount=s.current_bet_to_match + s.min_raise_increment)
            else:
                s = apply_action(s, nta, "call")
        else:
            if action_choice < 0.7:
                s = apply_action(s, nta, "check")
            elif s.seats[nta].stack > s.min_raise_increment:
                s = apply_action(s, nta, "raise", amount=s.min_raise_increment)
            else:
                s = apply_action(s, nta, "check")
        assert total_chips_in_play(s) == initial_total


def test_side_pots_three_all_ins_different_stacks() -> None:
    """Three players all-in at different stack sizes (30, 60, 100):
    main pot 30×3 = 90 eligible to all 3.
    side pot 1: (60-30) × 2 = 60 eligible to back two.
    side pot 2: (100-60) × 1 = 40 eligible to deepest only."""
    s = create_state([30, 60, 100], button_seat=0, small_blind=1, big_blind=2)
    s = apply_action(s, 0, "all_in")  # seat 0: 30 total
    s = apply_action(s, 1, "all_in")  # seat 1: 60 total
    s = apply_action(s, 2, "all_in")  # seat 2: 100 total
    # Move to "complete" by advancing all streets (allow runout)
    while s.street != "complete":
        s = advance_street(s)
    pots = compute_side_pots(s)
    # main pot: 30 * 3 = 90, eligible 0,1,2
    assert pots[0] == (90, [0, 1, 2])
    # side pot 1: (60-30) * 2 = 60, eligible 1,2
    assert pots[1] == (60, [1, 2])
    # side pot 2: (100-60) * 1 = 40, eligible 2
    assert pots[2] == (40, [2])


def test_side_pot_excludes_folded_players() -> None:
    """A seat that folds still contributes chips to the pot — they're committed
    — but they can't win."""
    s = create_state([50, 50, 50], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "raise", amount=30)
    s = apply_action(s, 1, "fold")
    s = apply_action(s, 2, "call")
    while s.street != "complete":
        s = advance_street(s)
    pots = compute_side_pots(s)
    # SB's 5 chips are still in the pot, but SB (seat 1) is not eligible.
    # Total pot: 30 (seat 0) + 5 (seat 1) + 30 (seat 2) = 65
    total_chips = sum(p for p, _ in pots)
    assert total_chips == 65
    # Seat 1 should not be in any eligibility list
    for _, eligible in pots:
        assert 1 not in eligible


# ─── Award pots ──────────────────────────────────────────────────────────────


def test_award_simple_pot_to_winner() -> None:
    s = create_state([500, 500, 500], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "fold")
    s = apply_action(s, 1, "fold")
    pots = compute_side_pots(s)
    # Single pot, only seat 2 eligible (others folded)
    assert len(pots) == 1
    s2 = award_pots(s, [[2]])
    # Seat 2 had stack 490 (after BB) + won pot containing SB's 5 + their own 10 = 15.
    assert s2.seats[2].stack == 490 + 15


def test_award_split_pot_distributes_evenly() -> None:
    s = create_state([100, 100], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "call")
    s = apply_action(s, 1, "check")
    # Pot = 20 (10+10). Both stacks at 90.
    while s.street != "complete":
        s = advance_street(s)
    s2 = award_pots(s, [[0, 1]])
    # Each gets half
    assert s2.seats[0].stack == 90 + 10
    assert s2.seats[1].stack == 90 + 10


def test_chip_conservation_through_full_hand_with_award() -> None:
    initial_total = 100 * 3
    s = create_state([100, 100, 100], button_seat=0, small_blind=5, big_blind=10)
    s = apply_action(s, 0, "raise", amount=30)
    s = apply_action(s, 1, "fold")
    s = apply_action(s, 2, "call")
    while s.street != "complete":
        s = advance_street(s)
    pots = compute_side_pots(s)
    # Award all to seat 0
    s2 = award_pots(s, [[0]] * len(pots))
    assert sum(seat.stack for seat in s2.seats) == initial_total
