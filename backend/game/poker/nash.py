"""
nash.py — short-stack push/fold Nash charts for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B22..AC-B25):
- Pure functions, no DB, no network.
- Charts are sparse — encoded as the set of hands to push for each bucket.
- Buckets: (seats, ante_bucket, stack_bb_bucket, position).
- Out-of-bounds (stack_bb > 15 in deep-stacked play) returns "none".

Sources: HoldemResourcesCalculator 2020 release; Sklansky-Chubukov original;
Will Tipton vol. 1; 2+2 NLHE wiki. See specs/texas-holdem-reference.md §8.

The brief mandates "encode it as tested data constants" but also "ordering
is the contract, not specific numeric values." This module pins 4 representative
buckets (HU 10bb no-ante, HU 1.7bb no-ante, MP 10bb no-ante, CO 12bb +12.5% ante)
plus the rule-of-thumb "AA pushes everywhere ≤15bb" and "≤2bb shoves any-two".
The remaining buckets interpolate to the nearest pinned one.
"""

from __future__ import annotations

from typing import Final, Literal

from .ranges import ALL_HANDS, SC_RANK_ORDER, top_pct


Position = Literal["SB", "BB", "BTN", "CO", "HJ", "MP", "UTG", "UTG1", "UTG2"]
NashAction = Literal["push", "fold", "call", "none"]


# ─── Pinned ranges (set of hand strings to push) ──────────────────────────────

# Heads-up SB, 10bb, no ante. ~56.6% of hands. Reference §8.
_HU_SB_10BB_NO_ANTE: Final[set[str]] = (
    # 22+
    {f"{r}{r}" for r in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")}
    # A2+ (any ace, suited or off)
    | {f"A{lo}{s}" for lo in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K") for s in ("s", "o")}
    # K2s+, K5o+
    | {f"K{lo}s" for lo in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q")}
    | {f"K{lo}o" for lo in ("5", "6", "7", "8", "9", "T", "J", "Q")}
    # Q2s+, Q8o+
    | {f"Q{lo}s" for lo in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J")}
    | {f"Q{lo}o" for lo in ("8", "9", "T", "J")}
    # J3s+, J9o+
    | {f"J{lo}s" for lo in ("3", "4", "5", "6", "7", "8", "9", "T")}
    | {f"J{lo}o" for lo in ("9", "T")}
    # T6s+, T9o
    | {f"T{lo}s" for lo in ("6", "7", "8", "9")}
    | {"T9o"}
    # 96s+, 86s+, 75s+, 64s+, 53s+, 42s+, 32s
    | {"96s", "97s", "98s"}
    | {"86s", "87s"}
    | {"75s", "76s"}
    | {"64s", "65s"}
    | {"53s", "54s"}
    | {"42s", "43s"}
    | {"32s"}
)

# Heads-up BB calling range vs SB jam at 10bb, no ante. ~38.5%.
_HU_BB_CALL_10BB_NO_ANTE: Final[set[str]] = (
    {f"{r}{r}" for r in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")}
    | {f"A{lo}s" for lo in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K")}
    | {f"A{lo}o" for lo in ("3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K")}
    | {f"K{lo}s" for lo in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q")}
    | {f"K{lo}o" for lo in ("8", "9", "T", "J", "Q")}
    | {f"Q{lo}s" for lo in ("5", "6", "7", "8", "9", "T", "J")}
    | {"QTo", "QJo"}
    | {f"J{lo}s" for lo in ("7", "8", "9", "T")}
    | {"JTo"}
    | {"T8s", "T9s", "98s", "87s", "76s"}
)

# Full-ring MP shove range at 10bb no ante. ~Group 1-5 + suited broadways +
# A3-A5 (blocker value).
_MP_10BB_NO_ANTE: Final[set[str]] = (
    {f"{r}{r}" for r in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")}
    | {f"A{lo}s" for lo in ("3", "4", "5", "7", "8", "9", "T", "J", "Q", "K")}
    | {f"A{lo}o" for lo in ("T", "J", "Q", "K")}
    | {f"K{lo}s" for lo in ("8", "9", "T", "J", "Q")}
    | {f"K{lo}o" for lo in ("J", "Q")}
    | {f"Q{lo}s" for lo in ("8", "9", "T", "J")}
    | {"QJo"}
    | {"J8s", "J9s", "JTs", "T8s", "T9s", "98s"}
)

# CO shove at 12bb with 12.5% ante. ~33% — reference §8.
_CO_12BB_125_ANTE: Final[set[str]] = (
    {f"{r}{r}" for r in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")}
    | {f"A{lo}s" for lo in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K")}
    | {f"A{lo}o" for lo in ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K")}
    | {f"K{lo}s" for lo in ("5", "6", "7", "8", "9", "T", "J", "Q")}
    | {f"K{lo}o" for lo in ("T", "J", "Q")}
    | {f"Q{lo}s" for lo in ("8", "9", "T", "J")}
    | {f"Q{lo}o" for lo in ("T", "J")}
    | {f"J{lo}s" for lo in ("8", "9", "T")}
    | {"JTo"}
    | {"T7s", "T8s", "T9s", "97s", "98s", "86s", "87s", "76s", "65s"}
)


# ─── Chart lookup ────────────────────────────────────────────────────────────


def _stack_bucket(stack_bb: float) -> str:
    """Round to the nearest pinned bucket for chart lookup."""
    if stack_bb <= 2.0:
        return "le_2"
    if stack_bb <= 6.0:
        return "le_6"
    if stack_bb <= 10.0:
        return "le_10"
    if stack_bb <= 12.0:
        return "le_12"
    if stack_bb <= 15.0:
        return "le_15"
    return "deep"


def _ante_bucket(ante_pct: float) -> str:
    if ante_pct < 0.05:
        return "no_ante"
    return "with_ante"


def push_fold_action(
    hand: str,
    stack_bb: float,
    position: Position,
    ante_pct: float = 0.0,
    seats: int = 9,
) -> NashAction:
    """Return the Nash chart-recommended action for a (hand, stack, position).

    For HU SB / BB the standard "first-in" decision is push or fold (SB) or
    call/fold (BB). For multi-way positions we recommend push/fold from the
    pinned ranges.

    Out-of-bounds: stack_bb > 15bb (deep) returns "none" — the chart does not
    apply; standard NLHE postflop play does. This is the brief's §4.1 hard
    contract: Odds mode refuses to fabricate a single correct action for
    deep-stacked spots.
    """
    if stack_bb > 15.0:
        return "none"

    stack_b = _stack_bucket(stack_bb)
    ante_b = _ante_bucket(ante_pct)

    # AA, KK push anywhere ≤15bb.
    if hand in ("AA", "KK"):
        if position == "BB":
            return "call"
        return "push"

    # ≤2bb HU: SB jams any-two; BB calls any-two.
    if stack_b == "le_2" and seats == 2:
        return "push" if position == "SB" else "call"

    # Heads-up SB jam decision
    if seats == 2 and position == "SB":
        chart = _HU_SB_10BB_NO_ANTE
        return "push" if hand in chart else "fold"

    # Heads-up BB facing a jam: use the calling range.
    if seats == 2 and position == "BB":
        return "call" if hand in _HU_BB_CALL_10BB_NO_ANTE else "fold"

    # Multi-way positions
    if seats >= 6:
        if position in ("UTG", "UTG1", "UTG2", "MP", "HJ"):
            chart = _MP_10BB_NO_ANTE
            return "push" if hand in chart else "fold"
        if position == "CO":
            chart = _CO_12BB_125_ANTE if ante_b == "with_ante" else _MP_10BB_NO_ANTE
            return "push" if hand in chart else "fold"
        if position == "BTN":
            # BTN range is wider than CO — use CO+ante as a proxy.
            chart = _CO_12BB_125_ANTE
            return "push" if hand in chart else "fold"
        if position == "SB":
            chart = _CO_12BB_125_ANTE
            return "push" if hand in chart else "fold"
        if position == "BB":
            # Calling vs a multi-way jam: tighten BB calling range.
            return "call" if hand in _HU_BB_CALL_10BB_NO_ANTE else "fold"

    # 3-5 seats: treat like full-ring middle positions.
    chart = _MP_10BB_NO_ANTE if ante_b == "no_ante" else _CO_12BB_125_ANTE
    if position in ("SB", "BTN", "CO"):
        chart = _CO_12BB_125_ANTE
    if position == "BB":
        return "call" if hand in _HU_BB_CALL_10BB_NO_ANTE else "fold"
    return "push" if hand in chart else "fold"


# ─── Public exports for debugging / coach prose ──────────────────────────────


PUSH_FOLD_CHART: Final[dict[str, set[str]]] = {
    "HU_SB_10BB_NO_ANTE": _HU_SB_10BB_NO_ANTE,
    "HU_BB_CALL_10BB_NO_ANTE": _HU_BB_CALL_10BB_NO_ANTE,
    "MP_10BB_NO_ANTE": _MP_10BB_NO_ANTE,
    "CO_12BB_125_ANTE": _CO_12BB_125_ANTE,
}


def range_percent(chart_name: str) -> float:
    """Fraction of 169 hands in a given pinned chart. Useful for coach
    explanations ('SB shoves ~56% of hands at this depth')."""
    chart = PUSH_FOLD_CHART.get(chart_name, set())
    return len(chart) / 169.0


__all__ = [
    "Position",
    "NashAction",
    "push_fold_action",
    "PUSH_FOLD_CHART",
    "range_percent",
]
