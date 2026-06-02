"""
prompts.py — Chipy prompt builders for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B44, AC-B45):
- Pure functions; no Anthropic call.
- build_reads_prompt names archetypes + estimated ranges.
- build_odds_prompt is deterministic-grounded only; refuses to fabricate
  a single correct action for deep postflop (mentions 'heuristic' or 'principle').
"""

from __future__ import annotations

from .archetypes import ArchetypeSpec
from .cards import Card, card_str
from .oracle import DecisionSnapshot


_SYSTEM_PROMPT_BASE = (
    "You are Chipy, an educational poker coach. Your job is to teach the player "
    "to think in ranges, equity, and pot odds — never to fabricate a single "
    "correct answer for postflop spots that don't have one. Be concise and "
    "explanatory. Always tag your verdict's confidence: DETERMINISTIC for "
    "≤15bb push/fold and pot-odds calls vs all-ins; HEURISTIC otherwise."
)


def _board_text(board: tuple[Card, ...]) -> str:
    if not board:
        return "(preflop, no board)"
    return " ".join(card_str(c) for c in board)


def _hole_text(hole: tuple[Card, Card]) -> str:
    return f"{card_str(hole[0])} {card_str(hole[1])}"


def build_odds_prompt(snapshot: DecisionSnapshot) -> tuple[str, str]:
    """Return (system_prompt, user_message) for Odds mode.

    Odds mode grounds advice in deterministic math only: pot odds, live
    equity, push/fold Nash for ≤15bb. Refuses to fabricate a single correct
    action for deep postflop — uses the words 'heuristic' or 'principle'.
    """
    system = _SYSTEM_PROMPT_BASE + (
        "\n\nMODE: ODDS. Ground every claim in pot-odds math, live equity, or "
        "short-stack Nash. For deep postflop (>15bb stack-effective, with bets "
        "below all-in), explicitly say 'this is heuristic, no single correct "
        "action' and give principles (pot control, MDF, range advantage)."
    )
    parts: list[str] = []
    parts.append(f"Hand: {_hole_text(snapshot.hole)} ({snapshot.hand_str})")
    parts.append(f"Position: {snapshot.position}; stack {snapshot.stack_bb:.1f}bb; "
                 f"pot {snapshot.pot_bb:.1f}bb; to call {snapshot.to_call_bb:.1f}bb.")
    parts.append(f"Board: {_board_text(snapshot.board)}")
    parts.append(f"Street: {snapshot.street}")
    parts.append(f"Live opponents: {snapshot.n_live_opponents}")
    if snapshot.live_equity is not None:
        parts.append(f"Live equity vs current opponents: {snapshot.live_equity:.1%}")
    if snapshot.is_bubble:
        parts.append("ICM stage: bubble (tighten calling ranges by ~4%; widen pressure spots).")
    if snapshot.stack_bb <= 15.0 and snapshot.street == "preflop":
        parts.append("This is a DETERMINISTIC short-stack push/fold spot.")
    else:
        parts.append("This is a HEURISTIC postflop / deep-stack spot — principles only, no single oracle.")
    user = "\n".join(parts)
    return system, user


def build_reads_prompt(
    snapshot: DecisionSnapshot,
    archetypes_by_seat: dict[int, ArchetypeSpec],
    last_actions_by_seat: dict[int, str] | None = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_message) for Reads mode.

    Reads mode references specific seat archetypes and what their actions
    likely mean. Names at least one archetype and one estimated-range
    descriptor.
    """
    system = _SYSTEM_PROMPT_BASE + (
        "\n\nMODE: READS. Reference specific seat archetypes by name, explain "
        "what each opponent's action likely means (bluff vs value vs trap vs "
        "semi-bluff), recommend hero's action against the archetype-estimated "
        "ranges, and call out exploit angles."
    )
    parts: list[str] = []
    parts.append(f"Hand: {_hole_text(snapshot.hole)} ({snapshot.hand_str})")
    parts.append(f"Position: {snapshot.position}; stack {snapshot.stack_bb:.1f}bb; "
                 f"pot {snapshot.pot_bb:.1f}bb; to call {snapshot.to_call_bb:.1f}bb.")
    parts.append(f"Board: {_board_text(snapshot.board)}")
    parts.append(f"Street: {snapshot.street}")
    if archetypes_by_seat:
        parts.append("Opponents at the table:")
        for seat_idx, spec in archetypes_by_seat.items():
            last = ""
            if last_actions_by_seat and seat_idx in last_actions_by_seat:
                last = f" (last action: {last_actions_by_seat[seat_idx]})"
            parts.append(
                f"  - Seat {seat_idx}: {spec.name} ({spec.animal or 'no animal'}) — "
                f"VPIP {spec.vpip:.0%}/PFR {spec.pfr:.0%}/AF {spec.af:.1f}. "
                f"{spec.description}{last}"
            )
    if snapshot.live_equity is not None:
        parts.append(f"Live equity vs estimated ranges: {snapshot.live_equity:.1%}")
    parts.append("Reference specific archetype range expectations and bet-sizing reads.")
    user = "\n".join(parts)
    return system, user


__all__ = ["build_reads_prompt", "build_odds_prompt"]
