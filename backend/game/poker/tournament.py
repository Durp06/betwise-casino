"""
tournament.py — tournament glue: blind schedule, payouts, button rotation.

Design constraints (specs/texas-holdem.md §AC-R1..R3 indirectly):
- Pure functions; no DB, no network.
- Default blind schedule + payout structure per reference §10.
- effective_bb computes "stack in bb" given the current level.
- next_button rotates the dealer button.
"""

from __future__ import annotations

from typing import Final


# ─── Blind schedule ─────────────────────────────────────────────────────────


# Each entry: (small_blind, big_blind, ante). Level advances every N hands
# (configurable; default 10).
BLIND_SCHEDULE_DEFAULT: Final[list[tuple[int, int, int]]] = [
    (10, 20, 0),       # Level 1
    (15, 30, 0),       # Level 2
    (25, 50, 0),       # Level 3
    (50, 100, 10),     # Level 4 — antes enter
    (75, 150, 15),     # Level 5
    (100, 200, 25),    # Level 6
    (150, 300, 25),    # Level 7
    (200, 400, 50),    # Level 8
    (300, 600, 75),    # Level 9
    (400, 800, 100),   # Level 10
    (600, 1200, 150),  # Level 11
    (1000, 2000, 200), # Level 12
    (1500, 3000, 300), # Level 13
    (2500, 5000, 500), # Level 14
    (4000, 8000, 800), # Level 15
]

DEFAULT_HANDS_PER_LEVEL: Final[int] = 10


def current_level(hand_number: int, hands_per_level: int = DEFAULT_HANDS_PER_LEVEL) -> tuple[int, int, int]:
    """Return (small_blind, big_blind, ante) for a given hand number.

    Hand 1..hands_per_level → level 1; hand_per_level+1..2*hands_per_level → level 2; etc.
    Caps at the last level in BLIND_SCHEDULE_DEFAULT.
    """
    if hand_number < 1:
        raise ValueError("hand_number must be ≥ 1")
    if hands_per_level < 1:
        raise ValueError("hands_per_level must be ≥ 1")
    level_index = (hand_number - 1) // hands_per_level
    level_index = min(level_index, len(BLIND_SCHEDULE_DEFAULT) - 1)
    return BLIND_SCHEDULE_DEFAULT[level_index]


def effective_bb(stack_chips: int, big_blind: int) -> float:
    """Stack expressed in big blinds."""
    if big_blind <= 0:
        raise ValueError("big_blind must be > 0")
    return stack_chips / big_blind


# ─── Payouts ─────────────────────────────────────────────────────────────────


# Maps seat-count → list of payout percentages (must sum to 100.0).
PAYOUT_STRUCTURE_BY_SEATS: Final[dict[int, list[float]]] = {
    2: [100.0],
    3: [70.0, 30.0],
    4: [65.0, 35.0],
    5: [60.0, 30.0, 10.0],
    6: [55.0, 30.0, 15.0],
    7: [50.0, 30.0, 20.0],
    8: [50.0, 30.0, 20.0],
}


def payout_pcts_for_seats(seats: int) -> list[float]:
    """Return the payout percentages for an SNG with `seats` seats."""
    if seats not in PAYOUT_STRUCTURE_BY_SEATS:
        # Fall back to nearest known
        keys = sorted(PAYOUT_STRUCTURE_BY_SEATS.keys())
        for k in keys:
            if seats <= k:
                return PAYOUT_STRUCTURE_BY_SEATS[k]
        return PAYOUT_STRUCTURE_BY_SEATS[keys[-1]]
    return PAYOUT_STRUCTURE_BY_SEATS[seats]


def payout_chips(prize_pool_cents: int, seats: int) -> list[int]:
    """Return prize amounts in cents per finish position.

    Rounds down to integer cents; gives the rounding remainder to 1st place.
    """
    pcts = payout_pcts_for_seats(seats)
    amounts = [int(prize_pool_cents * p / 100.0) for p in pcts]
    remainder = prize_pool_cents - sum(amounts)
    if amounts:
        amounts[0] += remainder
    return amounts


# ─── Button rotation ─────────────────────────────────────────────────────────


def next_button(button_seat: int, live_seats: list[int]) -> int:
    """Return the new button seat clockwise from current button, skipping
    busted (non-live) seats.

    `live_seats` is the list of currently-active seat indices (those with
    stack > 0 entering the next hand).
    """
    if not live_seats:
        raise ValueError("Cannot rotate button with no live seats")
    n = max(live_seats) + 1  # logical table size
    for offset in range(1, n + 1):
        candidate = (button_seat + offset) % n
        if candidate in live_seats:
            return candidate
    raise ValueError("Could not find live seat for next button")


def seat_position_label(seat_idx: int, button: int, seats: int) -> str:
    """Map seat index to position label given the current button.

    For seats from 2..9, returns one of: BTN, SB, BB, UTG, UTG1, UTG2, MP,
    HJ, CO. See reference §10.
    """
    if seats < 2 or seats > 9:
        raise ValueError("seats must be 2..9")
    offset = (seat_idx - button) % seats

    # HU (2 seats): BTN = SB, BB
    if seats == 2:
        return "BTN" if offset == 0 else "BB"

    # 3+: BTN, SB, BB, then increasing offsets are post-BB positions.
    # We walk left of the button (BTN→SB→BB→UTG→...→CO→back to BTN).
    if offset == 0:
        return "BTN"
    if offset == 1:
        return "SB"
    if offset == 2:
        return "BB"

    # Remaining: UTG / UTG1 / UTG2 / MP / HJ / CO. The exact label depends on seats.
    # Walk from BB+1 backwards to CO (which is offset = seats - 1 = button - 1).
    # Labels by seat count (offsets 3..seats-1):
    labels_by_seats: dict[int, list[str]] = {
        4: ["CO"],                                # offset 3 only
        5: ["UTG", "CO"],                         # offsets 3, 4
        6: ["UTG", "MP", "CO"],                   # 3, 4, 5
        7: ["UTG", "MP", "HJ", "CO"],             # 3, 4, 5, 6
        8: ["UTG", "UTG1", "MP", "HJ", "CO"],
        9: ["UTG", "UTG1", "UTG2", "MP", "HJ", "CO"],
    }
    labels = labels_by_seats[seats]
    idx = offset - 3
    return labels[idx]


__all__ = [
    "BLIND_SCHEDULE_DEFAULT",
    "DEFAULT_HANDS_PER_LEVEL",
    "PAYOUT_STRUCTURE_BY_SEATS",
    "current_level",
    "effective_bb",
    "payout_pcts_for_seats",
    "payout_chips",
    "next_button",
    "seat_position_label",
]
