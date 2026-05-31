"""
oracle.py — tiered correctness oracle for human poker decisions.

Design constraints (specs/texas-holdem.md §AC-B40..B43; brief §4.2 landmine):
- DETERMINISTIC vs HEURISTIC confidence tag on EVERY classification.
- DETERMINISTIC spots: ≤15bb push/fold, pot-odds vs all-in. Real EV-loss.
- HEURISTIC spots: deep postflop. Principle-based note only. Never penalize
  the streak (the brief mandates streaks count ONLY deterministic spots).
- ICM overlay near the bubble — tighter calling threshold.

This module is the educational core of the feature. Its output drives:
- streak (deterministic spots only)
- session review (chess.com-style classification + EV-loss for deterministic)
- coach's verbal verdict (Reads or Odds mode)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .cards import Card
from .nash import push_fold_action
from .pot_odds import required_equity


ConfidenceTier = Literal["DETERMINISTIC", "HEURISTIC"]
HumanAction = Literal["fold", "check", "call", "raise", "all_in"]
CoachMode = Literal["reads", "odds"]
Verdict = Literal["best", "good", "inaccuracy", "mistake", "blunder", "no_verdict"]


@dataclass(frozen=True)
class DecisionSnapshot:
    """Pure inputs to the oracle. The router builds this from the persisted
    state + the human's hole cards."""

    hole: tuple[Card, Card]
    board: tuple[Card, ...]
    street: Literal["preflop", "flop", "turn", "river"]
    position: str               # 'SB','BB','BTN','CO','HJ','MP','UTG','UTG1','UTG2'
    hand_str: str               # canonical, e.g. 'AKs', '77'
    stack_bb: float
    pot_bb: float
    to_call_bb: float
    n_live_opponents: int
    seats_remaining: int        # in tournament
    is_bubble: bool             # within one elimination of the money
    live_equity: Optional[float]  # provided by router via equity engine


@dataclass(frozen=True)
class DecisionClassification:
    """The verdict + supporting data."""

    confidence_tier: ConfidenceTier
    recommended_action: Optional[HumanAction]
    correct: Optional[bool]                  # None for HEURISTIC
    verdict: Verdict
    ev_loss_chips: Optional[int]             # None for HEURISTIC
    principle_note: Optional[str]            # populated for HEURISTIC
    coach_summary: str
    counts_toward_streak: bool


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _is_short_stack_pushfold(snapshot: DecisionSnapshot) -> bool:
    """Spot is DETERMINISTIC if stack ≤ 15bb and it's a first-in-or-call
    short-stack decision."""
    return snapshot.stack_bb <= 15.0 and snapshot.street == "preflop"


def _is_pot_odds_call_vs_all_in(snapshot: DecisionSnapshot) -> bool:
    """Spot is DETERMINISTIC if it's a clear pot-odds-call vs an all-in
    (postflop, hero is facing an all-in)."""
    if snapshot.to_call_bb <= 0:
        return False
    # If to_call equals (or nearly equals) hero's remaining stack, it's an all-in.
    return snapshot.to_call_bb >= snapshot.stack_bb * 0.95


def _icm_threshold_adjustment(snapshot: DecisionSnapshot) -> float:
    """Return the extra equity (in points, e.g. 0.03 = +3%) needed for an
    ICM-correct call relative to chip-EV. Heuristic — tightens near the
    bubble."""
    if snapshot.is_bubble:
        return 0.04
    return 0.0


# ─── Classification ─────────────────────────────────────────────────────────


def classify_decision(
    snapshot: DecisionSnapshot,
    human_action: HumanAction,
    mode: CoachMode = "odds",
) -> DecisionClassification:
    """Tiered correctness classification.

    DETERMINISTIC: hard correct/incorrect + EV-loss in chips.
    HEURISTIC: principle-based note only; no verdict, no streak penalty.
    """
    # ─── DETERMINISTIC: short-stack push/fold ──────────────────────────
    if _is_short_stack_pushfold(snapshot):
        recommended = push_fold_action(
            hand=snapshot.hand_str,
            stack_bb=snapshot.stack_bb,
            position=snapshot.position,  # type: ignore[arg-type]
            ante_pct=0.0,
            seats=snapshot.seats_remaining,
        )
        if recommended != "none":
            human_simple = "push" if human_action == "all_in" else ("call" if human_action == "call" else "fold")
            correct = human_simple == recommended
            ev_loss = 0 if correct else int(snapshot.stack_bb * 0.5)  # rough estimate
            verdict: Verdict = "best" if correct else "blunder"
            return DecisionClassification(
                confidence_tier="DETERMINISTIC",
                recommended_action=_simple_to_human_action(recommended),
                correct=correct,
                verdict=verdict,
                ev_loss_chips=ev_loss,
                principle_note=None,
                coach_summary=(
                    f"Short-stack ({snapshot.stack_bb:.1f}bb) Nash chart says {recommended}."
                ),
                counts_toward_streak=True,
            )

    # ─── DETERMINISTIC: pot-odds vs all-in (postflop) ──────────────────
    if _is_pot_odds_call_vs_all_in(snapshot) and snapshot.live_equity is not None:
        # Required equity considering ICM overlay
        pot_before_call = snapshot.pot_bb
        opp_bet = snapshot.to_call_bb
        chip_ev_threshold = required_equity(pot_before_call, opp_bet)
        threshold = chip_ev_threshold + _icm_threshold_adjustment(snapshot)
        should_call = snapshot.live_equity >= threshold
        human_called = human_action in ("call", "all_in")
        correct = human_called == should_call
        ev_diff = abs(snapshot.live_equity - threshold)
        ev_loss = 0 if correct else int(ev_diff * (pot_before_call + opp_bet) * 100)
        verdict = "best" if correct else ("mistake" if ev_diff < 0.10 else "blunder")
        return DecisionClassification(
            confidence_tier="DETERMINISTIC",
            recommended_action="call" if should_call else "fold",
            correct=correct,
            verdict=verdict,
            ev_loss_chips=ev_loss,
            principle_note=None,
            coach_summary=(
                f"Pot odds need {threshold:.1%} equity; you have {snapshot.live_equity:.1%}. "
                f"{'Call' if should_call else 'Fold'} is correct."
            ),
            counts_toward_streak=True,
        )

    # ─── HEURISTIC: deep postflop / general spots ──────────────────────
    note = _build_heuristic_note(snapshot, human_action)
    return DecisionClassification(
        confidence_tier="HEURISTIC",
        recommended_action=None,
        correct=None,
        verdict="no_verdict",
        ev_loss_chips=None,
        principle_note=note,
        coach_summary=note,
        counts_toward_streak=False,
    )


def _simple_to_human_action(simple: str) -> HumanAction:
    if simple == "push":
        return "all_in"
    if simple == "call":
        return "call"
    return "fold"


def _build_heuristic_note(snapshot: DecisionSnapshot, human_action: HumanAction) -> str:
    parts: list[str] = []
    if snapshot.live_equity is not None:
        parts.append(f"Live equity: {snapshot.live_equity:.0%}.")
    if snapshot.to_call_bb > 0:
        chip_threshold = required_equity(snapshot.pot_bb, snapshot.to_call_bb)
        parts.append(f"Pot odds need {chip_threshold:.0%} equity to call.")
    if snapshot.is_bubble:
        parts.append("Bubble — tighten calling ranges; widen pressure with fold equity.")
    parts.append("Deep postflop is heuristic — no single correct action; use principles.")
    return " ".join(parts)


__all__ = [
    "ConfidenceTier",
    "HumanAction",
    "CoachMode",
    "Verdict",
    "DecisionSnapshot",
    "DecisionClassification",
    "classify_decision",
]
