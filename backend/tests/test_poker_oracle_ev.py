"""
test_poker_oracle_ev.py — failing tests for the new EV-grading paths in oracle.py (PR 1).

Maps 1:1 to acceptance criteria G-1 through G-7, G-BC2, G-BC3 from
specs/poker-review-pr1-equity-engine.md §5.

All G-* tests exercise the new `live_equity is not None` EV branch that does
NOT exist yet in oracle.py.  They are expected to fail on current main because
the verdicts produced by the new branch don't exist.

G-BC1 (the full existing test_poker_oracle.py suite remains green) is a
structural constraint enforced by not modifying that file; it is verified
separately by running that suite.

Snapshot construction note:
Every snapshot in this file must avoid the two existing DETERMINISTIC
short-circuits so the test reaches the new EV branch (or the existing
HEURISTIC fall-through for BC2):

  1. _is_short_stack_pushfold: fires when stack_bb ≤ 15 AND street == "preflop"
     → always use stack_bb = 100 and a postflop street.

  2. _is_pot_odds_call_vs_all_in: fires when to_call_bb >= stack_bb * 0.95
     → always use to_call_bb < stack_bb * 0.95.
     With stack_bb = 100 and to_call_bb ≤ 20, the ratio is ≤ 0.20 < 0.95 ✓
"""
from __future__ import annotations

import pytest

from backend.game.poker.cards import parse_card
from backend.game.poker.oracle import (
    DecisionClassification,
    DecisionSnapshot,
    classify_decision,
)
from backend.game.poker.pot_odds import required_equity as _required_equity


# ---------------------------------------------------------------------------
# Helpers (mirror test_poker_oracle.py conventions exactly)
# ---------------------------------------------------------------------------


def C(s: str):
    """Parse a compact card string to a Card dict."""
    return parse_card(s)


def _snap(
    hand_str: str = "AKs",
    hole=("As", "Ks"),
    board=("Qd", "Jc", "7h"),
    street: str = "flop",
    position: str = "BTN",
    stack_bb: float = 100.0,
    pot_bb: float = 10.0,
    to_call_bb: float = 5.0,
    n_live_opponents: int = 1,
    seats_remaining: int = 8,
    is_bubble: bool = False,
    live_equity: float | None = None,
) -> DecisionSnapshot:
    """Build a deep-stack (100bb) postflop DecisionSnapshot.

    Defaults avoid BOTH existing DETERMINISTIC short-circuits:
      - stack_bb = 100 + postflop street  →  push/fold bucket does NOT fire.
      - to_call_bb = 5, stack_bb = 100   →  5 < 95 = 100*0.95  →  all-in bucket does NOT fire.
    """
    return DecisionSnapshot(
        hole=(C(hole[0]), C(hole[1])),
        board=tuple(C(s) for s in board),
        street=street,
        position=position,
        hand_str=hand_str,
        stack_bb=stack_bb,
        pot_bb=pot_bb,
        to_call_bb=to_call_bb,
        n_live_opponents=n_live_opponents,
        seats_remaining=seats_remaining,
        is_bubble=is_bubble,
        live_equity=live_equity,
    )


# ---------------------------------------------------------------------------
# G-1: clearly −EV call → verdict in {mistake, blunder}, ev_loss_bb > 0
#
# Pot = 10bb, to_call = 5bb → required equity = 5/(10+5+5) = 0.25.
# Hero's live_equity = 0.05 (far below 0.25).  Correct action = fold.
# Hero action = call → clearly wrong.  ev_loss_bb > 0.
# ---------------------------------------------------------------------------

def test_g1_negative_ev_call_is_mistake_or_blunder() -> None:
    """G-1: call with equity far below required → verdict in {mistake, blunder}, ev_loss_bb > 0."""
    snap = _snap(
        hand_str="72o",
        hole=("7s", "2c"),
        board=("Ah", "Kd", "Qc"),
        street="flop",
        pot_bb=10.0,
        to_call_bb=5.0,    # required equity = 5/(10+5+5) = 0.25
        stack_bb=100.0,
        live_equity=0.05,  # far below 0.25 required
    )
    result = classify_decision(snap, "call", "odds")
    assert result.verdict in {"mistake", "blunder"}, (
        f"Expected mistake or blunder for a −EV call, got verdict={result.verdict!r}"
    )
    assert result.ev_loss_bb is not None, "ev_loss_bb should be populated for EV verdicts"
    assert result.ev_loss_bb > 0, f"ev_loss_bb should be positive, got {result.ev_loss_bb}"


# ---------------------------------------------------------------------------
# G-2: +EV value call → verdict == "best", ev_loss_bb ≈ 0
#
# Pot = 10bb, to_call = 5bb → required equity = 0.25.
# Hero's live_equity = 0.80 (far above required).  Call is correct.
# ev_loss_bb should be ≈ 0 (no EV lost).
# ---------------------------------------------------------------------------

def test_g2_positive_ev_call_is_best() -> None:
    """G-2: call with equity comfortably above required → verdict == 'best', ev_loss_bb ≈ 0."""
    snap = _snap(
        hand_str="AA",
        hole=("Ah", "Ad"),
        board=("Kd", "7c", "2h"),
        street="flop",
        pot_bb=10.0,
        to_call_bb=5.0,    # required equity = 0.25
        stack_bb=100.0,
        live_equity=0.80,  # well above required
    )
    result = classify_decision(snap, "call", "odds")
    assert result.verdict == "best", (
        f"Expected 'best' for a clearly +EV call, got verdict={result.verdict!r}"
    )
    assert result.ev_loss_bb is not None, "ev_loss_bb should be populated for EV verdicts"
    assert result.ev_loss_bb == pytest.approx(0.0, abs=0.1), (
        f"ev_loss_bb should be ≈ 0 for a correct call, got {result.ev_loss_bb}"
    )


# ---------------------------------------------------------------------------
# G-3: correct fold of trash → verdict == "best", recommended_action == "fold"
#
# Same spot as G-1 (equity 0.05 << required 0.25) but hero folds — correct.
# ---------------------------------------------------------------------------

def test_g3_correct_fold_of_trash_is_best() -> None:
    """G-3: fold when equity far below required → verdict == 'best', recommended == 'fold'."""
    snap = _snap(
        hand_str="72o",
        hole=("7s", "2c"),
        board=("Ah", "Kd", "Qc"),
        street="flop",
        pot_bb=10.0,
        to_call_bb=5.0,
        stack_bb=100.0,
        live_equity=0.05,  # well below required 0.25
    )
    result = classify_decision(snap, "fold", "odds")
    assert result.verdict == "best", (
        f"Expected 'best' for a correct fold, got verdict={result.verdict!r}"
    )
    assert result.recommended_action == "fold", (
        f"Expected recommended_action='fold', got {result.recommended_action!r}"
    )


# ---------------------------------------------------------------------------
# G-4: calling a clear fold spot → verdict is at least "mistake"
#
# Equity = 0.05, required = 0.25 (pot=10, call=5).  ev_loss is large.
# Verdict must be "mistake" or "blunder" (the upper end of _bucket_delta_bb).
# ---------------------------------------------------------------------------

def test_g4_calling_clear_fold_spot_is_at_least_mistake() -> None:
    """G-4: call with equity far below required → verdict is 'mistake' or 'blunder'."""
    snap = _snap(
        hand_str="72o",
        hole=("7s", "2c"),
        board=("Ah", "Kd", "Qc"),
        street="flop",
        pot_bb=10.0,
        to_call_bb=5.0,
        stack_bb=100.0,
        live_equity=0.05,
    )
    result = classify_decision(snap, "call", "odds")
    assert result.verdict in {"mistake", "blunder"}, (
        f"Expected at least 'mistake', got verdict={result.verdict!r}"
    )


# ---------------------------------------------------------------------------
# G-5: marginal call near threshold → verdict in {good, inaccuracy}
#
# Pot = 10bb, to_call = 5bb → required = 0.25.
# equity = 0.28 (just above required) → correct call, small EV edge.
# The small EV gap should land in "good" or "inaccuracy".
#
# We also check the just-below case (equity = 0.22, should be inaccuracy/
# mistake for calling when slightly below required).
# ---------------------------------------------------------------------------

def test_g5_marginal_call_near_threshold_is_good_or_inaccuracy() -> None:
    """G-5: equity just above required → verdict in {good, inaccuracy} for the call."""
    # required_equity(10, 5) = 5/(10+5+5) = 5/20 = 0.25
    # equity = 0.28 → small positive edge → "good" or "inaccuracy"
    snap = _snap(
        hand_str="JTs",
        hole=("Jh", "Th"),
        board=("Qd", "9c", "3h"),
        street="flop",
        pot_bb=10.0,
        to_call_bb=5.0,
        stack_bb=100.0,
        live_equity=0.28,  # just above required 0.25
    )
    result = classify_decision(snap, "call", "odds")
    assert result.verdict in {"best", "good", "inaccuracy"}, (
        f"Expected best/good/inaccuracy for marginal call just above threshold, "
        f"got verdict={result.verdict!r}"
    )
    # The EV gain is small so it should NOT be blunder/mistake
    assert result.verdict not in {"blunder", "mistake"}, (
        f"A marginally correct call should not be mistake/blunder, got {result.verdict!r}"
    )


# ---------------------------------------------------------------------------
# G-6: contextual multi-street bet → no_verdict + HEURISTIC + no streak penalty
#
# Hero raises/bets with medium equity (0.45) — a genuinely contextual spot.
# The simplified model cannot resolve this → no_verdict, HEURISTIC,
# counts_toward_streak False, non-empty principle_note.
# ---------------------------------------------------------------------------

def test_g6_contextual_bet_returns_no_verdict_heuristic() -> None:
    """G-6: bet/raise with medium equity and ambiguous sizing → no_verdict, HEURISTIC.

    Also verifies the additive new fields exist on the result (requires Task 6).
    The ev_loss_bb field should be None for a no_verdict HEURISTIC spot —
    the oracle does not compute EV for bet/raise contextual spots.
    """
    snap = _snap(
        hand_str="JTs",
        hole=("Jh", "Th"),
        board=("Qd", "9c", "3h", "2d"),  # turn
        street="turn",
        pot_bb=10.0,
        to_call_bb=0.0,  # hero is the aggressor (bet, not a call)
        stack_bb=100.0,
        live_equity=0.45,  # medium — contextual
    )
    result = classify_decision(snap, "raise", "odds")
    assert result.verdict == "no_verdict", (
        f"Expected no_verdict for contextual bet/raise, got verdict={result.verdict!r}"
    )
    assert result.confidence_tier == "HEURISTIC", (
        f"Expected HEURISTIC tier for contextual bet, got {result.confidence_tier!r}"
    )
    assert result.counts_toward_streak is False, (
        "HEURISTIC bet/raise should not count toward streak"
    )
    assert result.principle_note is not None and len(result.principle_note) > 0, (
        "principle_note should be populated for HEURISTIC verdicts"
    )
    # The new additive fields must exist (Task 6). ev_loss_bb is None for
    # contextual no_verdict spots — the oracle does not compute EV for bets.
    assert hasattr(result, "ev_loss_bb"), (
        "DecisionClassification missing 'ev_loss_bb' field (requires Task 6)"
    )
    assert result.ev_loss_bb is None, (
        f"ev_loss_bb should be None for a no_verdict HEURISTIC spot, got {result.ev_loss_bb}"
    )


# ---------------------------------------------------------------------------
# G-7: new fields populated on an EV verdict (G-2 spot)
#
# For a +EV call verdict (G-2 parameters), the result must have:
#   - equity is not None
#   - required_equity is not None
#   - ev_loss_bb is not None
#   - required_equity value == pot_odds required + ICM adj (non-bubble → 0)
# ---------------------------------------------------------------------------

def test_g7_new_fields_populated_on_ev_verdict() -> None:
    """G-7: equity, required_equity, ev_loss_bb are all non-None and consistent on +EV call."""
    pot_bb = 10.0
    to_call_bb = 5.0
    live_eq = 0.80
    is_bubble = False

    snap = _snap(
        hand_str="AA",
        hole=("Ah", "Ad"),
        board=("Kd", "7c", "2h"),
        street="flop",
        pot_bb=pot_bb,
        to_call_bb=to_call_bb,
        stack_bb=100.0,
        is_bubble=is_bubble,
        live_equity=live_eq,
    )
    result = classify_decision(snap, "call", "odds")

    # All three new fields must be populated
    assert result.equity is not None, "equity field should be populated for EV verdicts"
    assert result.required_equity is not None, "required_equity field should be populated"
    assert result.ev_loss_bb is not None, "ev_loss_bb field should be populated"

    # equity should match the live_equity we passed in
    assert result.equity == pytest.approx(live_eq, abs=1e-9), (
        f"equity field {result.equity} should equal live_equity {live_eq}"
    )

    # required_equity = pot_odds required + ICM adjustment (0 for non-bubble)
    expected_req = _required_equity(pot_bb, to_call_bb)  # no ICM adj on non-bubble
    assert result.required_equity == pytest.approx(expected_req, abs=1e-6), (
        f"required_equity {result.required_equity} does not match expected "
        f"required_equity({pot_bb}, {to_call_bb}) = {expected_req}"
    )


# ---------------------------------------------------------------------------
# G-BC2: live_equity=None deep-postflop → still HEURISTIC no_verdict, no streak
#
# This is the behavioural-identity check: every existing router caller passes
# live_equity=None.  Adding the new EV branch must NOT break this path.
# ---------------------------------------------------------------------------

def test_gbc2_live_equity_none_deep_postflop_is_heuristic_no_verdict() -> None:
    """G-BC2: live_equity=None deep postflop → confidence_tier HEURISTIC, verdict no_verdict.

    Also verifies the new additive fields exist (requires Task 6) and are None
    for the None-equity path — ensuring the existing router callers are unaffected.
    """
    snap = _snap(
        hand_str="AKs",
        hole=("As", "Ks"),
        board=("Qd", "Jc", "7h"),
        street="flop",
        pot_bb=10.0,
        to_call_bb=5.0,
        stack_bb=100.0,
        live_equity=None,  # what all current callers pass
    )
    result = classify_decision(snap, "call", "odds")
    assert result.confidence_tier == "HEURISTIC", (
        f"live_equity=None path must remain HEURISTIC, got {result.confidence_tier!r}"
    )
    assert result.verdict == "no_verdict", (
        f"live_equity=None path must return no_verdict, got {result.verdict!r}"
    )
    assert result.counts_toward_streak is False, (
        "live_equity=None path must not count toward streak"
    )
    # New fields (Task 6) must exist; must be None when live_equity is None.
    assert hasattr(result, "equity"), (
        "DecisionClassification missing 'equity' field (requires Task 6)"
    )
    assert result.equity is None, (
        f"equity should be None when live_equity=None, got {result.equity}"
    )
    assert hasattr(result, "ev_loss_bb"), (
        "DecisionClassification missing 'ev_loss_bb' field (requires Task 6)"
    )
    assert result.ev_loss_bb is None, (
        f"ev_loss_bb should be None when live_equity=None, got {result.ev_loss_bb}"
    )


# ---------------------------------------------------------------------------
# G-BC3: constructing DecisionClassification with only pre-existing kwargs works
#
# Guards against accidentally making the new optional fields required,
# which would break existing live call-sites that construct the dataclass.
# ---------------------------------------------------------------------------

def test_gbc3_decision_classification_optional_new_fields_have_defaults() -> None:
    """G-BC3: DecisionClassification can be constructed without the new optional fields."""
    # This must not raise TypeError (no missing required arguments)
    dc = DecisionClassification(
        confidence_tier="HEURISTIC",
        recommended_action=None,
        correct=None,
        verdict="no_verdict",
        ev_loss_chips=None,
        principle_note="Deep postflop — heuristic only.",
        coach_summary="Deep postflop — heuristic only.",
        counts_toward_streak=False,
    )
    # New fields should exist and default to None
    assert hasattr(dc, "equity"), "DecisionClassification missing new 'equity' field"
    assert hasattr(dc, "required_equity"), "DecisionClassification missing 'required_equity' field"
    assert hasattr(dc, "ev_loss_bb"), "DecisionClassification missing 'ev_loss_bb' field"
    assert hasattr(dc, "explanation"), "DecisionClassification missing 'explanation' field"
    assert dc.equity is None, f"equity should default to None, got {dc.equity}"
    assert dc.required_equity is None, f"required_equity should default to None, got {dc.required_equity}"
    assert dc.ev_loss_bb is None, f"ev_loss_bb should default to None, got {dc.ev_loss_bb}"
    assert dc.explanation is None, f"explanation should default to None, got {dc.explanation}"
