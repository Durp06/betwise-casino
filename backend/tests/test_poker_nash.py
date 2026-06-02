"""
test_poker_nash.py — covers AC-B22..AC-B25 from specs/texas-holdem.md.
"""
from __future__ import annotations

import pytest

from backend.game.poker.nash import (
    PUSH_FOLD_CHART,
    push_fold_action,
    range_percent,
)


# ─── HU SB 10bb pinned cases (AC-B22) ─────────────────────────────────────────


def test_aa_pushes_everywhere() -> None:
    """AA is a profitable shove at every position / stack ≤ 15bb."""
    for position in ("SB", "BTN", "CO", "MP", "UTG"):
        for stack in (1.5, 5, 10, 12, 15):
            assert push_fold_action("AA", stack, position, ante_pct=0, seats=9) == "push"


def test_hu_sb_10bb_aa_pushes() -> None:
    assert push_fold_action("AA", 10, "SB", 0, 2) == "push"


def test_hu_sb_10bb_a2s_pushes() -> None:
    """A2s is in the published HU 10bb SB range (~56% of hands)."""
    assert push_fold_action("A2s", 10, "SB", 0, 2) == "push"


def test_hu_sb_10bb_32o_folds() -> None:
    """32o is at the very bottom of HU 10bb SB range — folds."""
    assert push_fold_action("32o", 10, "SB", 0, 2) == "fold"


def test_hu_sb_10bb_72o_folds() -> None:
    """72o is below the threshold."""
    assert push_fold_action("72o", 10, "SB", 0, 2) == "fold"


# ─── HU 1.7bb shoves any-two (AC-B23) ─────────────────────────────────────────


def test_hu_sb_1bb_shoves_any_two() -> None:
    """At ≤2bb HU, SB shoves any two cards (and BB calls any two)."""
    for hand in ("72o", "32o", "53o", "AKo", "AA"):
        assert push_fold_action(hand, 1.5, "SB", 0, 2) == "push"


def test_hu_bb_1bb_calls_any_two() -> None:
    for hand in ("72o", "32o", "QJo", "AA"):
        assert push_fold_action(hand, 1.5, "BB", 0, 2) == "call"


# ─── CO 12bb + ante widens (AC-B24) ──────────────────────────────────────────


def test_co_12bb_with_ante_kto_pushes() -> None:
    """With 12.5% ante, the CO 12bb shove range widens to include KTo+
    (reference §8). Without antes, only KJo+ is in range."""
    assert push_fold_action("KTo", 12, "CO", ante_pct=0.125, seats=9) == "push"


def test_co_12bb_no_ante_kto_folds() -> None:
    """Without antes the CO uses the tighter (MP-equivalent) range; KTo folds."""
    assert push_fold_action("KTo", 12, "CO", ante_pct=0.0, seats=9) == "fold"


def test_co_12bb_ante_widens_more_hands() -> None:
    """The +ante chart strictly contains more hands than the no-ante chart."""
    co_ante_hands = PUSH_FOLD_CHART["CO_12BB_125_ANTE"]
    mp_no_ante_hands = PUSH_FOLD_CHART["MP_10BB_NO_ANTE"]
    # CO+ante range should include weak-Ax / suited-K rows that MP_no_ante does not.
    assert "A2o" in co_ante_hands
    assert "A2o" not in mp_no_ante_hands


# ─── Out-of-bounds: deep stacks return "none" (AC-B25) ───────────────────────


def test_deep_stack_returns_none() -> None:
    """Above 15bb the chart does not apply — Odds mode refuses to fabricate
    an oracle (brief §4.1)."""
    for stack in (16, 20, 50, 100):
        for hand in ("AKs", "JJ", "32o"):
            result = push_fold_action(hand, stack, "BTN", 0, 9)
            assert result == "none", f"Expected 'none' for {hand} at {stack}bb, got {result!r}"


def test_aa_kk_still_push_at_15bb() -> None:
    """The 15bb cliff — AA still recommends push."""
    assert push_fold_action("AA", 15, "SB", 0, 2) == "push"


def test_aa_kk_returns_none_above_15bb() -> None:
    """Above 15bb the chart doesn't apply — Odds mode refuses to fabricate
    a single correct action even for AA."""
    assert push_fold_action("AA", 25, "BTN", 0, 9) == "none"


# ─── Multi-way UTG tight ─────────────────────────────────────────────────────


def test_utg_10bb_weak_ace_folds() -> None:
    """A3o should NOT be in MP/UTG shove range at 10bb no ante — dominated."""
    # Reference §8 principle: weak offsuit aces are losing UTG pushes at 10bb.
    result = push_fold_action("A3o", 10, "UTG", 0, 9)
    assert result == "fold"


def test_utg_10bb_pp_pushes() -> None:
    """22+ pushes from UTG at 10bb."""
    assert push_fold_action("22", 10, "UTG", 0, 9) == "push"
    assert push_fold_action("55", 10, "UTG", 0, 9) == "push"


# ─── Range_percent sanity ────────────────────────────────────────────────────


def test_range_percent_hu_sb_around_55() -> None:
    """HU SB 10bb range is ~56% of hands per reference §8."""
    pct = range_percent("HU_SB_10BB_NO_ANTE")
    assert 0.50 <= pct <= 0.65


def test_range_percent_hu_bb_calling_around_38() -> None:
    pct = range_percent("HU_BB_CALL_10BB_NO_ANTE")
    assert 0.30 <= pct <= 0.45


def test_range_percent_co_ante_around_33() -> None:
    pct = range_percent("CO_12BB_125_ANTE")
    assert 0.25 <= pct <= 0.45
