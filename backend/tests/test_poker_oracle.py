"""
test_poker_oracle.py — covers AC-B40..B43 from specs/texas-holdem.md.
"""
from __future__ import annotations

import pytest

from backend.game.poker.cards import parse_card
from backend.game.poker.oracle import (
    DecisionSnapshot,
    classify_decision,
)


def C(s):
    return parse_card(s)


def _snap(
    hand_str="AA",
    hole=("As", "Ah"),
    board=(),
    street="preflop",
    position="SB",
    stack_bb=10.0,
    pot_bb=1.5,
    to_call_bb=0.0,
    n_live_opponents=1,
    seats_remaining=2,
    is_bubble=False,
    live_equity=None,
):
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


# ─── DETERMINISTIC short-stack push/fold (AC-B40) ────────────────────────────


def test_short_stack_aa_push_is_deterministic_correct() -> None:
    snap = _snap(hand_str="AA", hole=("As", "Ah"), stack_bb=10, position="SB", seats_remaining=2)
    c = classify_decision(snap, "all_in", "odds")
    assert c.confidence_tier == "DETERMINISTIC"
    assert c.correct is True
    assert c.verdict == "best"
    assert c.counts_toward_streak is True


def test_short_stack_aa_fold_is_deterministic_blunder() -> None:
    snap = _snap(hand_str="AA", hole=("As", "Ah"), stack_bb=10, position="SB", seats_remaining=2)
    c = classify_decision(snap, "fold", "odds")
    assert c.confidence_tier == "DETERMINISTIC"
    assert c.correct is False
    assert c.verdict == "blunder"
    assert c.ev_loss_chips is not None and c.ev_loss_chips > 0


def test_short_stack_junk_fold_is_correct() -> None:
    snap = _snap(hand_str="32o", hole=("3s", "2h"), stack_bb=10, position="UTG", seats_remaining=9)
    c = classify_decision(snap, "fold", "odds")
    assert c.confidence_tier == "DETERMINISTIC"
    assert c.correct is True


# ─── DETERMINISTIC pot-odds call vs all-in (AC-B41) ──────────────────────────


def test_pot_odds_call_with_enough_equity_is_correct() -> None:
    # Hero has 50% equity facing an all-in for half their stack at pot odds 33%.
    snap = _snap(
        hand_str="88",
        hole=("8s", "8h"),
        board=("Kh", "8d", "3c"),  # set of 8s
        street="flop",
        position="BTN",
        stack_bb=10.0,
        pot_bb=5.0,
        to_call_bb=10.0,  # opp went all-in for hero's stack
        n_live_opponents=1,
        seats_remaining=3,
        live_equity=0.85,  # set vs anything = huge
    )
    c = classify_decision(snap, "call", "odds")
    assert c.confidence_tier == "DETERMINISTIC"
    assert c.correct is True


def test_pot_odds_fold_with_insufficient_equity_is_correct() -> None:
    snap = _snap(
        hand_str="72o",
        hole=("7s", "2c"),
        board=("Kh", "8d", "3c"),
        street="flop",
        position="BTN",
        stack_bb=10.0,
        pot_bb=5.0,
        to_call_bb=10.0,
        n_live_opponents=1,
        seats_remaining=3,
        live_equity=0.05,
    )
    c = classify_decision(snap, "fold", "odds")
    assert c.confidence_tier == "DETERMINISTIC"
    assert c.correct is True


# ─── HEURISTIC deep postflop (AC-B42) ────────────────────────────────────────


def test_deep_postflop_is_heuristic() -> None:
    snap = _snap(
        hand_str="AKs",
        hole=("As", "Ks"),
        board=("Qd", "Jc", "7h"),
        street="flop",
        position="BTN",
        stack_bb=100.0,    # deep
        pot_bb=10.0,
        to_call_bb=5.0,    # not all-in
        n_live_opponents=1,
        seats_remaining=8,
        live_equity=0.45,
    )
    c = classify_decision(snap, "call", "odds")
    assert c.confidence_tier == "HEURISTIC"
    assert c.correct is None
    assert c.verdict == "no_verdict"
    assert c.counts_toward_streak is False
    assert c.principle_note is not None and len(c.principle_note) > 0


def test_heuristic_principle_note_mentions_useful_concepts() -> None:
    snap = _snap(
        hand_str="JTs",
        hole=("Jh", "Th"),
        board=("Qh", "9c", "2d"),
        street="flop",
        position="BTN",
        stack_bb=100.0,
        pot_bb=10.0,
        to_call_bb=5.0,
        is_bubble=True,
        live_equity=0.55,
    )
    c = classify_decision(snap, "call", "odds")
    # Principle note should mention something concrete (equity, pot odds, or
    # bubble dynamics).
    note = c.principle_note or ""
    assert any(token in note.lower() for token in ("equity", "pot odds", "bubble", "heuristic", "principle"))


# ─── ICM overlay (AC-B43) ────────────────────────────────────────────────────


def test_icm_overlay_tightens_calling_threshold() -> None:
    """Near the bubble, the equity threshold for a 'call' verdict should be
    stricter than chip-EV. With live_equity exactly at chip-EV break-even,
    calling on a bubble should be classified as incorrect."""
    # Chip-EV pot-odds break-even for pot=10, opp_bet=20 (overbet) → 0.4
    # ICM bubble adjustment: +0.04 → threshold 0.44.
    snap_bubble = _snap(
        hand_str="AKs",
        hole=("As", "Ks"),
        board=("Qd", "Jc", "7h", "2s", "3d"),
        street="river",
        position="BTN",
        stack_bb=20.0,
        pot_bb=10.0,
        to_call_bb=20.0,  # all-in for hero's stack
        seats_remaining=3,
        is_bubble=True,
        live_equity=0.41,  # just above chip-EV (0.40) but below ICM (0.44)
    )
    c_call = classify_decision(snap_bubble, "call", "odds")
    assert c_call.confidence_tier == "DETERMINISTIC"
    assert c_call.correct is False  # because bubble pushes threshold above 0.41

    snap_normal = _snap(
        hand_str="AKs",
        hole=("As", "Ks"),
        board=("Qd", "Jc", "7h", "2s", "3d"),
        street="river",
        position="BTN",
        stack_bb=20.0,
        pot_bb=10.0,
        to_call_bb=20.0,
        seats_remaining=8,
        is_bubble=False,
        live_equity=0.41,
    )
    c_normal = classify_decision(snap_normal, "call", "odds")
    # Outside bubble, 0.41 ≥ chip-EV 0.40 → correct call
    assert c_normal.confidence_tier == "DETERMINISTIC"
    assert c_normal.correct is True


# ─── Streak invariants (brief §4.2) ───────────────────────────────────────────


def test_streak_counts_deterministic_only() -> None:
    # Heuristic doesn't count
    snap_h = _snap(stack_bb=100, street="flop", pot_bb=5, to_call_bb=2, live_equity=0.5,
                   board=("Qd", "Jc", "7h"))
    assert classify_decision(snap_h, "call", "odds").counts_toward_streak is False

    # Deterministic short-stack: counts
    snap_d = _snap(stack_bb=10, position="SB", seats_remaining=2, hand_str="AA", hole=("As", "Ah"))
    assert classify_decision(snap_d, "all_in", "odds").counts_toward_streak is True
