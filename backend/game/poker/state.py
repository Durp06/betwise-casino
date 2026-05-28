"""
state.py — betting state machine for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B31..AC-B38):
- Immutable BettingState; apply_action returns a new state.
- Pure functions; no DB, no network.
- Chip conservation invariant: sum(stacks) + sum(pots) + sum(current bets) ==
  initial total chips, after every transition.
- Min-raise rule: a raise must be ≥ the previous raise increment, except
  an all-in for less than the min raise does NOT reopen betting.
- Heads-up reversal: BTN posts SB preflop, acts first preflop, acts last postflop.
- Side pots: when multiple players are all-in at different commitment levels,
  the pot splits into a main pot and N side pots eligible to the deepest
  players.

The state machine intentionally does NOT know about archetypes or the
evaluator; it is the pure mechanics layer. The router glues archetypes
(decisions) + state (mechanics) + evaluator (showdown) together.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Optional


Street = Literal["preflop", "flop", "turn", "river", "complete"]
SeatAction = Literal["fold", "check", "call", "raise", "all_in", "post_blind", "post_ante"]


# ─── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Seat:
    """One seat at the table for one hand."""

    seat_number: int           # 0-based index, stable across the tournament
    stack: int                 # chips currently in this seat's stack
    current_bet: int = 0       # chips committed THIS street, sitting in front of seat
    total_committed: int = 0   # chips committed THIS hand across all streets
    is_folded: bool = False
    is_all_in: bool = False
    has_acted_this_street: bool = False


@dataclass(frozen=True)
class ActionRecord:
    """One entry in the action log — what a seat did and when."""

    seat_number: int
    street: Street
    action: SeatAction
    amount: int = 0  # for raises and all-ins: chips paid (current_bet delta)


@dataclass(frozen=True)
class BettingState:
    """The whole pot state. Immutable; replace with new state via apply_action."""

    seats: tuple[Seat, ...]
    button_seat: int
    small_blind: int
    big_blind: int
    ante: int
    street: Street
    current_bet_to_match: int  # the chip-level all seats must call to stay in
    min_raise_increment: int   # the size of the last raise; next raise ≥ this
    last_aggressor_seat: Optional[int]  # who made the last raise
    pot_committed: int         # chips in the pot from previous streets
    action_log: tuple[ActionRecord, ...] = field(default_factory=tuple)

    @property
    def n_seats(self) -> int:
        return len(self.seats)

    def live_seats(self) -> list[Seat]:
        """Seats not folded and not (out of stack and not all-in for this hand)."""
        return [s for s in self.seats if not s.is_folded]

    def active_seats(self) -> list[Seat]:
        """Seats that can still act this street — not folded, not all-in."""
        return [s for s in self.seats if not s.is_folded and not s.is_all_in]


# ─── Initialization ─────────────────────────────────────────────────────────


def create_state(
    starting_stacks: list[int],
    button_seat: int,
    small_blind: int,
    big_blind: int,
    ante: int = 0,
) -> BettingState:
    """Initialize a new hand. Posts antes + blinds, deducts from stacks,
    sets current_bet_to_match = big_blind, and chooses the first-to-act seat.
    """
    n = len(starting_stacks)
    if n < 2:
        raise ValueError("Need at least 2 seats")

    seats = [
        Seat(seat_number=i, stack=starting_stacks[i])
        for i in range(n)
    ]
    state = BettingState(
        seats=tuple(seats),
        button_seat=button_seat,
        small_blind=small_blind,
        big_blind=big_blind,
        ante=ante,
        street="preflop",
        current_bet_to_match=0,
        min_raise_increment=big_blind,
        last_aggressor_seat=None,
        pot_committed=0,
    )

    # Post antes (if any)
    if ante > 0:
        state = _post_antes(state, ante)

    # Post small + big blinds. HU: BTN posts SB, opposite seat posts BB.
    sb_seat = _sb_seat(button_seat, n)
    bb_seat = _bb_seat(button_seat, n)
    state = _post_blind(state, sb_seat, small_blind, label="sb")
    state = _post_blind(state, bb_seat, big_blind, label="bb")

    # Set current_bet_to_match to BB
    state = replace(state, current_bet_to_match=big_blind)
    return state


def _sb_seat(button: int, n: int) -> int:
    """Heads-up: button posts SB. 3+ handed: next clockwise from button."""
    if n == 2:
        return button
    return (button + 1) % n


def _bb_seat(button: int, n: int) -> int:
    """Heads-up: opposite of button. 3+ handed: two clockwise from button."""
    if n == 2:
        return (button + 1) % n
    return (button + 2) % n


def _post_antes(state: BettingState, ante: int) -> BettingState:
    new_seats = []
    pot_delta = 0
    for s in state.seats:
        actual = min(ante, s.stack)
        new_seats.append(replace(
            s,
            stack=s.stack - actual,
            total_committed=s.total_committed + actual,
            is_all_in=(s.stack - actual == 0 and actual > 0),
        ))
        pot_delta += actual
    new_log = state.action_log + tuple(
        ActionRecord(seat_number=i, street="preflop", action="post_ante", amount=min(ante, state.seats[i].stack))
        for i in range(state.n_seats)
    )
    return replace(state, seats=tuple(new_seats), pot_committed=state.pot_committed + pot_delta, action_log=new_log)


def _post_blind(state: BettingState, seat_idx: int, blind: int, label: str) -> BettingState:
    s = state.seats[seat_idx]
    actual = min(blind, s.stack)
    new_s = replace(
        s,
        stack=s.stack - actual,
        current_bet=s.current_bet + actual,
        total_committed=s.total_committed + actual,
        is_all_in=(s.stack - actual == 0 and actual > 0),
    )
    new_seats = list(state.seats)
    new_seats[seat_idx] = new_s
    new_log = state.action_log + (
        ActionRecord(seat_number=seat_idx, street="preflop", action="post_blind", amount=actual),
    )
    return replace(state, seats=tuple(new_seats), action_log=new_log)


# ─── Action application ─────────────────────────────────────────────────────


def apply_action(
    state: BettingState,
    seat_idx: int,
    action: SeatAction,
    amount: int = 0,
) -> BettingState:
    """Apply an action by a seat. Returns a new BettingState.

    Raises ValueError if the action is illegal (out-of-turn, insufficient
    chips, raise below min-raise that isn't an all-in).
    """
    if seat_idx >= state.n_seats:
        raise ValueError(f"Invalid seat {seat_idx}")
    seat = state.seats[seat_idx]
    if seat.is_folded:
        raise ValueError("Folded seat cannot act")
    if seat.is_all_in:
        raise ValueError("All-in seat cannot act")

    to_call = state.current_bet_to_match - seat.current_bet

    if action == "fold":
        return _apply_fold(state, seat_idx)
    if action == "check":
        if to_call > 0:
            raise ValueError(f"Cannot check; must call {to_call}")
        return _apply_check(state, seat_idx)
    if action == "call":
        return _apply_call(state, seat_idx, to_call)
    if action == "raise":
        return _apply_raise(state, seat_idx, amount, to_call)
    if action == "all_in":
        return _apply_all_in(state, seat_idx)
    raise ValueError(f"Unknown action: {action}")


def _apply_fold(state: BettingState, seat_idx: int) -> BettingState:
    new_seats = list(state.seats)
    new_seats[seat_idx] = replace(state.seats[seat_idx], is_folded=True, has_acted_this_street=True)
    new_log = state.action_log + (
        ActionRecord(seat_number=seat_idx, street=state.street, action="fold"),
    )
    return replace(state, seats=tuple(new_seats), action_log=new_log)


def _apply_check(state: BettingState, seat_idx: int) -> BettingState:
    new_seats = list(state.seats)
    new_seats[seat_idx] = replace(state.seats[seat_idx], has_acted_this_street=True)
    new_log = state.action_log + (
        ActionRecord(seat_number=seat_idx, street=state.street, action="check"),
    )
    return replace(state, seats=tuple(new_seats), action_log=new_log)


def _apply_call(state: BettingState, seat_idx: int, to_call: int) -> BettingState:
    seat = state.seats[seat_idx]
    actual = min(to_call, seat.stack)
    new_seats = list(state.seats)
    new_seats[seat_idx] = replace(
        seat,
        stack=seat.stack - actual,
        current_bet=seat.current_bet + actual,
        total_committed=seat.total_committed + actual,
        is_all_in=(seat.stack - actual == 0),
        has_acted_this_street=True,
    )
    new_log = state.action_log + (
        ActionRecord(seat_number=seat_idx, street=state.street, action="call", amount=actual),
    )
    return replace(state, seats=tuple(new_seats), action_log=new_log)


def _apply_raise(state: BettingState, seat_idx: int, raise_to: int, to_call: int) -> BettingState:
    """raise_to is the new current_bet level the raiser is moving to."""
    seat = state.seats[seat_idx]
    if raise_to <= state.current_bet_to_match:
        raise ValueError(f"Raise must be > current bet {state.current_bet_to_match}")
    raise_increment = raise_to - state.current_bet_to_match
    delta_for_seat = raise_to - seat.current_bet

    if delta_for_seat > seat.stack:
        # Not enough stack — convert to all-in
        return _apply_all_in(state, seat_idx)

    if raise_increment < state.min_raise_increment:
        raise ValueError(
            f"Raise increment {raise_increment} below min raise {state.min_raise_increment}"
        )

    new_seats = list(state.seats)
    new_seats[seat_idx] = replace(
        seat,
        stack=seat.stack - delta_for_seat,
        current_bet=raise_to,
        total_committed=seat.total_committed + delta_for_seat,
        is_all_in=(seat.stack - delta_for_seat == 0),
        has_acted_this_street=True,
    )
    # A new raise reopens action — reset has_acted_this_street for everyone else
    new_seats = [
        replace(s, has_acted_this_street=False) if (i != seat_idx and not s.is_folded and not s.is_all_in) else s
        for i, s in enumerate(new_seats)
    ]
    new_log = state.action_log + (
        ActionRecord(seat_number=seat_idx, street=state.street, action="raise", amount=delta_for_seat),
    )
    return replace(
        state,
        seats=tuple(new_seats),
        current_bet_to_match=raise_to,
        min_raise_increment=raise_increment,
        last_aggressor_seat=seat_idx,
        action_log=new_log,
    )


def _apply_all_in(state: BettingState, seat_idx: int) -> BettingState:
    seat = state.seats[seat_idx]
    if seat.stack <= 0:
        raise ValueError("Seat has no chips to go all-in")
    new_bet_level = seat.current_bet + seat.stack
    delta = seat.stack
    raise_increment = new_bet_level - state.current_bet_to_match

    new_seats = list(state.seats)
    new_seats[seat_idx] = replace(
        seat,
        stack=0,
        current_bet=new_bet_level,
        total_committed=seat.total_committed + delta,
        is_all_in=True,
        has_acted_this_street=True,
    )

    new_log = state.action_log + (
        ActionRecord(seat_number=seat_idx, street=state.street, action="all_in", amount=delta),
    )

    # If the all-in is for MORE than the current bet AND the increment ≥ min_raise,
    # it's a true raise — reopens action.
    if new_bet_level > state.current_bet_to_match and raise_increment >= state.min_raise_increment:
        new_seats = [
            replace(s, has_acted_this_street=False)
            if (i != seat_idx and not s.is_folded and not s.is_all_in)
            else s
            for i, s in enumerate(new_seats)
        ]
        return replace(
            state,
            seats=tuple(new_seats),
            current_bet_to_match=new_bet_level,
            min_raise_increment=raise_increment,
            last_aggressor_seat=seat_idx,
            action_log=new_log,
        )

    # All-in for less than a min-raise — current_bet_to_match increases but
    # action does NOT reopen for already-acted players.
    new_bet_to_match = max(state.current_bet_to_match, new_bet_level)
    return replace(
        state,
        seats=tuple(new_seats),
        current_bet_to_match=new_bet_to_match,
        action_log=new_log,
    )


# ─── Street logic ────────────────────────────────────────────────────────────


def street_closed(state: BettingState) -> bool:
    """A street is closed when every active seat has acted and matched the
    current bet."""
    if state.street == "complete":
        return True

    # Only one (or zero) live seat → hand ends
    if len(state.live_seats()) <= 1:
        return True

    # All live seats either all-in or have acted and matched
    for s in state.seats:
        if s.is_folded or s.is_all_in:
            continue
        if not s.has_acted_this_street:
            return False
        if s.current_bet < state.current_bet_to_match:
            return False
    return True


def next_to_act(state: BettingState) -> Optional[int]:
    """Return the seat index that should act next. None if street is closed."""
    if street_closed(state):
        return None
    n = state.n_seats
    # First-to-act per street:
    # Preflop in HU: SB (=button) acts first.
    # Preflop in 3+: UTG (left of BB) acts first; first action is left of BB.
    # Postflop in HU: BB acts first.
    # Postflop in 3+: first live seat left of button.
    if state.last_aggressor_seat is not None:
        start = (state.last_aggressor_seat + 1) % n
    else:
        if state.street == "preflop":
            bb_seat = _bb_seat(state.button_seat, n)
            start = (bb_seat + 1) % n
        else:
            if n == 2:
                start = (state.button_seat + 1) % n  # postflop HU: BB first
            else:
                start = (state.button_seat + 1) % n  # SB acts first postflop
    # Walk clockwise to find the next active seat that hasn't acted-and-matched
    for offset in range(n):
        idx = (start + offset) % n
        s = state.seats[idx]
        if s.is_folded or s.is_all_in:
            continue
        if not s.has_acted_this_street or s.current_bet < state.current_bet_to_match:
            return idx
    return None


def advance_street(state: BettingState) -> BettingState:
    """Move to the next street: collect current_bets into pot_committed,
    reset has_acted_this_street, current_bet, last_aggressor."""
    next_street_map: dict[Street, Street] = {
        "preflop": "flop",
        "flop": "turn",
        "turn": "river",
        "river": "complete",
        "complete": "complete",
    }
    pot_delta = sum(s.current_bet for s in state.seats)
    new_seats = tuple(
        replace(s, current_bet=0, has_acted_this_street=False)
        for s in state.seats
    )
    new_street = next_street_map[state.street]
    return replace(
        state,
        seats=new_seats,
        pot_committed=state.pot_committed + pot_delta,
        current_bet_to_match=0,
        min_raise_increment=state.big_blind,
        last_aggressor_seat=None,
        street=new_street,
    )


# ─── Side pots + chip conservation ───────────────────────────────────────────


def compute_side_pots(state: BettingState) -> list[tuple[int, list[int]]]:
    """Return list of (pot_chips, eligible_seat_indices) pairs.

    Algorithm: at showdown, group by total_committed. The lowest commitment
    level among contenders defines the main pot (everyone contributes
    min(commit, level)). Then strip that level off and repeat.
    """
    # Collect commitments per seat (all seats, even folded — folded seats
    # contribute to pots but cannot win them)
    commitments = [(i, s.total_committed) for i, s in enumerate(state.seats)]
    folded = {i for i, s in enumerate(state.seats) if s.is_folded}

    # Sort unique commitment levels
    sorted_levels = sorted({c for _, c in commitments if c > 0})

    raw_pots: list[tuple[int, list[int]]] = []
    prev_level = 0
    for level in sorted_levels:
        delta = level - prev_level
        contributors = [i for i, c in commitments if c >= level]
        pot_amount = delta * len(contributors)
        eligible = [i for i in contributors if i not in folded]
        if pot_amount > 0:
            raw_pots.append((pot_amount, eligible))
        prev_level = level

    # Merge consecutive pots that have the same eligibility list. This collapses
    # e.g. (folded SB level + BB level → single pot to the remaining seat) into
    # one logical pot for the consumer.
    merged: list[tuple[int, list[int]]] = []
    for pot_amount, eligible in raw_pots:
        if merged and merged[-1][1] == eligible:
            prev_amount, prev_eligible = merged[-1]
            merged[-1] = (prev_amount + pot_amount, prev_eligible)
        else:
            merged.append((pot_amount, eligible))
    return merged


def total_chips_in_play(state: BettingState) -> int:
    """Chip conservation invariant: sum of stacks + sum of current bets +
    pot_committed should equal the original total starting chips."""
    return (
        sum(s.stack for s in state.seats)
        + sum(s.current_bet for s in state.seats)
        + state.pot_committed
    )


# ─── Award pots ──────────────────────────────────────────────────────────────


def award_pots(
    state: BettingState,
    winners_per_pot: list[list[int]],
) -> BettingState:
    """Award each pot to the winner(s) — handles split pots.

    `winners_per_pot` is a list of lists; each inner list is the seat indices
    that win that pot. Odd chips go to the first seat clockwise from button.
    """
    pots = compute_side_pots(state)
    if len(winners_per_pot) != len(pots):
        raise ValueError(
            f"winners_per_pot has {len(winners_per_pot)} entries; expected {len(pots)}"
        )

    new_stacks = [s.stack for s in state.seats]
    for (pot_amount, eligible), winners in zip(pots, winners_per_pot, strict=False):
        if not winners:
            continue
        per_winner = pot_amount // len(winners)
        remainder = pot_amount - per_winner * len(winners)
        for w in winners:
            new_stacks[w] += per_winner
        # Odd chip: first winner clockwise from button
        if remainder > 0:
            ordered = sorted(winners, key=lambda i: (i - state.button_seat - 1) % state.n_seats)
            for j in range(remainder):
                new_stacks[ordered[j % len(ordered)]] += 1

    new_seats = tuple(
        replace(s, stack=new_stacks[i]) for i, s in enumerate(state.seats)
    )
    return replace(state, seats=new_seats, pot_committed=0)


__all__ = [
    "Street",
    "SeatAction",
    "Seat",
    "ActionRecord",
    "BettingState",
    "create_state",
    "apply_action",
    "street_closed",
    "next_to_act",
    "advance_street",
    "compute_side_pots",
    "total_chips_in_play",
    "award_pots",
]
