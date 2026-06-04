"""
oracle.py — tiered correctness oracle for human poker decisions.

Design constraints (specs/texas-holdem.md §AC-B40..B43; brief §4.2 landmine):
- DETERMINISTIC vs HEURISTIC confidence tag on EVERY classification.
- DETERMINISTIC spots: ≤15bb push/fold, pot-odds vs all-in. Real EV-loss.
- HEURISTIC spots: deep postflop. Principle-based note only. Never penalize
  the streak (the brief mandates streaks count ONLY deterministic spots).
- ICM overlay near the bubble — tighter calling threshold.

Extended (specs/poker-review-pr1-equity-engine.md §4.3):
- When live_equity is not None AND neither existing DETERMINISTIC short-circuit
  fires, grade ordinary call/check/fold via real EV (EV(call) vs EV(fold))
  and bet/raise via a simplified semi-bluff model.
- The live_equity=None path is byte-for-byte behaviorally identical to current
  main — no existing tests change behavior.
- New verdict fields (equity, required_equity, ev_loss_bb, explanation) are
  additive and optional with None defaults.

This module is the educational core of the feature. Its output drives:
- streak (deterministic spots only)
- session review (chess.com-style classification + EV-loss for deterministic)
- coach's verbal verdict (Reads or Odds mode)
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    """The verdict + supporting data.

    The four new fields (equity, required_equity, ev_loss_bb, explanation) are
    additive and optional — they default to None so every existing construction
    site (live callers + existing tests) continues to compile unchanged.
    """

    confidence_tier: ConfidenceTier
    recommended_action: Optional[HumanAction]
    correct: Optional[bool]                  # None for HEURISTIC
    verdict: Verdict
    ev_loss_chips: Optional[int]             # None for HEURISTIC
    principle_note: Optional[str]            # populated for HEURISTIC
    coach_summary: str
    counts_toward_streak: bool
    # Additive fields — populated only for EV-graded spots (Task 6 / §4.5)
    equity: Optional[float] = field(default=None)
    required_equity: Optional[float] = field(default=None)
    ev_loss_bb: Optional[float] = field(default=None)
    explanation: Optional[str] = field(default=None)


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


def _bucket_delta_bb(ev_loss_bb: float) -> Verdict:
    """Map an EV-loss in big blinds to a verdict tier.

    Ported from backend/game/blackjack/review.py::_bucket_delta, re-tuned
    to big-blind units (specs/poker-review-pr1-equity-engine.md §4.4).
    Thresholds are monotone — move boundaries, never special-case tests.
    """
    if ev_loss_bb <= 0.05:
        return "best"
    if ev_loss_bb <= 0.25:
        return "good"
    if ev_loss_bb <= 1.0:
        return "inaccuracy"
    if ev_loss_bb <= 3.0:
        return "mistake"
    return "blunder"


# ─── Classification ─────────────────────────────────────────────────────────


def classify_decision(
    snapshot: DecisionSnapshot,
    human_action: HumanAction,
    mode: CoachMode = "odds",
) -> DecisionClassification:
    """Tiered correctness classification.

    DETERMINISTIC: hard correct/incorrect + EV-loss in chips.
    HEURISTIC: principle-based note only; no verdict, no streak penalty.

    Extended: when snapshot.live_equity is not None and neither existing
    DETERMINISTIC short-circuit fires, grades call/check/fold via real EV.
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

    # ─── NEW: EV-based call/check/fold grading (live_equity provided) ──
    if snapshot.live_equity is not None:
        return _classify_with_equity(snapshot, human_action, mode)

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


def _classify_with_equity(
    snapshot: DecisionSnapshot,
    human_action: HumanAction,
    mode: CoachMode,
) -> DecisionClassification:
    """Grade a decision when live_equity is available.

    Call/check/fold facing a bet → deterministic EV grading.
    Bet/raise → simplified semi-bluff model (mostly no_verdict in v1).
    Check with no bet → no_verdict (checking free is not gradable without
    a bet-or-check-back model).
    """
    equity = snapshot.live_equity  # guaranteed not None at this point
    assert equity is not None

    # ─── bet/raise → simplified semi-bluff model (mostly no_verdict) ──
    # all_in as an aggressor reaches here (all_in *calls* are caught earlier by
    # the pot-odds-vs-all-in DETERMINISTIC bucket). Route it through the same
    # semi-bluff model instead of letting it fall through to the catch-all.
    if human_action in ("raise", "all_in"):
        return _classify_bet_raise(snapshot, human_action, equity, mode)

    # ─── check with no bet → free check, cannot grade aggression choice ─
    if human_action == "check" and snapshot.to_call_bb == 0:
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

    # ─── call / fold facing a bet (to_call_bb > 0) ────────────────────
    if snapshot.to_call_bb > 0 and human_action in ("call", "fold", "check"):
        return _classify_call_or_fold(snapshot, human_action, equity, mode)

    # ─── fallback for unhandled combinations ──────────────────────────
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


def _classify_call_or_fold(
    snapshot: DecisionSnapshot,
    human_action: HumanAction,
    equity: float,
    mode: CoachMode,
) -> DecisionClassification:
    """EV-based grading for call/fold facing a bet.

    pot_bb is the pot BEFORE the opponent's bet (same convention as
    required_equity). The final pot after the opponent bets to_call_bb and
    hero calls to_call_bb is therefore (pot_bb + 2 * to_call_bb).

        EV(call) = equity * (pot_bb + 2 * to_call_bb) - to_call_bb
        EV(fold) = 0
        Required equity = required_equity(pot_bb, to_call_bb) + ICM adjustment
        Best action = call if equity >= required, else fold.

    This makes the EV break-even (EV(call) == 0) land exactly at
    equity == required_equity, keeping the magnitude consistent with the
    direction. Using (pot_bb + to_call_bb) would break even at the wrong
    equity and systematically mis-scale ev_loss_bb.
    """
    pot_bb = snapshot.pot_bb
    to_call_bb = snapshot.to_call_bb
    icm_adj = _icm_threshold_adjustment(snapshot)
    req_eq = required_equity(pot_bb, to_call_bb) + icm_adj

    ev_call = equity * (pot_bb + 2 * to_call_bb) - to_call_bb
    ev_fold = 0.0

    best_action: HumanAction = "call" if equity >= req_eq else "fold"
    ev_best = ev_call if best_action == "call" else ev_fold

    # EV of the action the player actually took
    if human_action == "call":
        ev_played = ev_call
    else:  # fold or check treated as fold in this branch
        ev_played = ev_fold

    ev_loss = abs(ev_best - ev_played)
    verdict = _bucket_delta_bb(ev_loss)
    correct = human_action == best_action or (human_action == "check" and best_action == "fold")

    summary = (
        f"Pot odds need {req_eq:.1%} equity; you have {equity:.1%}. "
        f"{'Call' if best_action == 'call' else 'Fold'} is correct."
    )

    return DecisionClassification(
        confidence_tier="DETERMINISTIC",
        recommended_action=best_action,
        correct=correct,
        verdict=verdict,
        ev_loss_chips=int(ev_loss * 100),  # convert bb to fake-cent chips (100 per bb)
        principle_note=None,
        coach_summary=summary,
        counts_toward_streak=True,
        equity=equity,
        required_equity=req_eq,
        ev_loss_bb=ev_loss,
        explanation=summary,
    )


def _classify_bet_raise(
    snapshot: DecisionSnapshot,
    human_action: HumanAction,
    equity: float,
    mode: CoachMode,
) -> DecisionClassification:
    """Simplified semi-bluff model for bet/raise decisions.

    v1 grades only the obvious value-bet case; everything else returns
    no_verdict (HEURISTIC) because actual fold equity is unknowable without
    a villain-response model.  This is the design's honesty boundary.
    """
    note = _build_heuristic_note(snapshot, human_action)
    note = note + " Bet/raise grading requires villain response model — principle-based only."
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
