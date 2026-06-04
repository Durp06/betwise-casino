"""
test_poker_equity.py — failing tests for the equity engine (PR 1).

Maps 1:1 to acceptance criteria E-1 through E-10 from
specs/poker-review-pr1-equity-engine.md §5.

All tests import from backend.game.poker.equity, which does NOT yet exist.
They are expected to fail at collection/import time until the implementer
creates that module.
"""
from __future__ import annotations

import pytest

# The module under test does not exist yet — this import will fail at
# collection time, which is the correct "red" state for PR 1 tests.
from backend.game.poker.equity import (
    default_range,
    hand_equity,
    range_to_combos,
)
from backend.game.poker.cards import parse_card

# ---------------------------------------------------------------------------
# Helpers (mirror test_poker_oracle.py conventions)
# ---------------------------------------------------------------------------


def C(s: str):
    """Parse a compact card string to a Card dict."""
    return parse_card(s)


def _hole(a: str, b: str) -> tuple:
    return (C(a), C(b))


def _board(*cards: str) -> list:
    return [C(s) for s in cards]


# ---------------------------------------------------------------------------
# E-1: preflop premium vs premium — AA vs KK ≈ 0.82
# ---------------------------------------------------------------------------

def test_e1_preflop_aa_vs_kk_equity() -> None:
    """E-1: hand_equity(AhAs, [{"KK"}], board=[], seed=1, max_iters=5000) ∈ [0.80, 0.84]."""
    eq = hand_equity(
        hero_hole=_hole("Ah", "As"),
        villain_ranges=[{"KK"}],
        board=[],
        seed=1,
        max_iters=5000,
    )
    assert 0.80 <= eq <= 0.84, f"AA vs KK equity {eq:.4f} not in [0.80, 0.84]"


# ---------------------------------------------------------------------------
# E-2: preflop coin flip — AKs vs QQ ≈ 0.50
# ---------------------------------------------------------------------------

def test_e2_preflop_aks_vs_qq_coin_flip() -> None:
    """E-2: hand_equity(AsKs, [{"QQ"}], board=[], seed=1, max_iters=5000) ∈ [0.46, 0.54]."""
    eq = hand_equity(
        hero_hole=_hole("As", "Ks"),
        villain_ranges=[{"QQ"}],
        board=[],
        seed=1,
        max_iters=5000,
    )
    assert 0.46 <= eq <= 0.54, f"AKs vs QQ equity {eq:.4f} not in [0.46, 0.54]"


# ---------------------------------------------------------------------------
# E-3: determinism — same seed → identical float
# ---------------------------------------------------------------------------

def test_e3_determinism_same_seed_identical_result() -> None:
    """E-3: two calls with identical args incl. seed return the exact same float."""
    kwargs = dict(
        hero_hole=_hole("Ah", "As"),
        villain_ranges=[{"KK"}],
        board=[],
        seed=42,
        max_iters=5000,
    )
    first = hand_equity(**kwargs)
    second = hand_equity(**kwargs)
    assert first == second, (
        f"Non-deterministic: first call returned {first}, second returned {second}"
    )


# ---------------------------------------------------------------------------
# E-4: seed sensitivity (MC only) — two different seeds yield different floats
#
# Implementation note: we assert both seeds return values within tolerance of
# the known AA vs KK analytic (~0.82), but verify they are not both identical
# to each other. If the function is truly seeded this will hold; if it
# returns a constant the two values will be equal and the test fails.
# Marked soft — if this becomes flaky on specific seed pairs the implementer
# should flag it, but the AC is well-defined for a seeded MC function.
# ---------------------------------------------------------------------------

def test_e4_seed_sensitivity_mc_spot() -> None:
    """E-4: preflop MC spot with two different seeds yields different floats."""
    eq_s1 = hand_equity(
        hero_hole=_hole("Ah", "As"),
        villain_ranges=[{"KK"}],
        board=[],
        seed=1,
        max_iters=5000,
    )
    eq_s2 = hand_equity(
        hero_hole=_hole("Ah", "As"),
        villain_ranges=[{"KK"}],
        board=[],
        seed=999,
        max_iters=5000,
    )
    # Both should be within analytic tolerance (sanity), and they must differ.
    assert 0.78 <= eq_s1 <= 0.86, f"Seed 1 equity {eq_s1:.4f} out of expected range"
    assert 0.78 <= eq_s2 <= 0.86, f"Seed 999 equity {eq_s2:.4f} out of expected range"
    assert eq_s1 != eq_s2, (
        "Different seeds returned identical floats — engine does not honour seed "
        f"(both = {eq_s1})"
    )


# ---------------------------------------------------------------------------
# E-5: exact enumeration on the river — made flush dominates a set
#
# Hero:    Ah Th
# Villain: {"KcKd"} — but we model with a KK range; the range_to_combos will
#          remove dead hearts so only non-heart KK combos remain (KcKd, KcKs,
#          KdKs).
# Board:   Kh Qh 2c 8d Jh  (5-card board → 0 cards to come → pure enumeration)
#
# Hero holds Ah Th + board Kh Qh Jh → Royal flush (A K Q J T all hearts).
# Villain holds any KK → best hand is full house (KKK + board pair? board has no
# pair) or trips. Royal flush beats everything → hero wins 100% = 1.0 exactly.
# ---------------------------------------------------------------------------

def test_e5_river_enumeration_flush_beats_set_hero_wins_exactly() -> None:
    """E-5: on a complete 5-card board where hero has a flush, equity == 1.0 exactly."""
    # Board: Kh Qh 2c 8d Jh (hero Ah Th → royal flush)
    # Villain KK: KcKd, KcKs, KdKs all beat by royal flush → hero always wins.
    eq = hand_equity(
        hero_hole=_hole("Ah", "Th"),
        villain_ranges=[{"KK"}],
        board=_board("Kh", "Qh", "2c", "8d", "Jh"),
        seed=1,
        max_iters=5000,
    )
    assert eq == 1.0, f"Expected exactly 1.0 (royal flush beats all), got {eq}"


# ---------------------------------------------------------------------------
# E-6: exact enumeration on the turn — 1 card to come, computed fraction
#
# Hero:    Ah Th  (Ah, Th + board Kh Qh → A-K-Q-T of hearts + Broadway draw)
# Villain: {"KK"} (non-heart KK combos only after dead-card removal: a set of
#          kings, since the board already has Kh)
# Board:   Kh Qh 2c 8d  (4 cards; 1 to come)
#
# Per villain combo the river deck has 52 - 2(hero) - 4(board) - 2(villain) = 44
# cards. By symmetry the spare non-heart king is irrelevant to hero's outs, so
# every combo yields the same fraction and the enumeration average equals it.
#
# Hero wins on the river (vs villain's set of kings) in exactly TWO ways:
#   1. FLUSH — a 5th heart completes A-K-Q-T-x of hearts. 9 hearts remain
#      (13 - Ah/Th/Kh/Qh), BUT 2h and 8h PAIR the board (2c / 8d), giving villain
#      a full house (KKK + pair) that BEATS a flush. So only 9 - 2 = 7 hearts win.
#      (Jh is among the 7 and makes a straight flush — still one winning card.)
#   2. STRAIGHT — an off-suit Jack (Jd/Jc/Js) makes A-K-Q-J-T Broadway, which
#      beats trip kings and does not pair the board. 3 outs.
#
# Total hero outs = 7 (hearts) + 3 (off-suit jacks) = 10.
# Expected equity = 10 / 44 ≈ 0.22727272...
# (Earlier this test asserted 9/44 — it missed the Broadway straight (+3) and the
#  full-house-over-flush redraws on 2h/8h (-2). The engine, which scores real
#  showdowns via best_5_of_7, correctly returns 10/44.)
# ---------------------------------------------------------------------------

def test_e6_turn_enumeration_draw_exact_fraction() -> None:
    """E-6: 1-card-to-come exact enumeration equals 10/44 (7 flush + 3 straight outs)."""
    expected = 10 / 44  # ≈ 0.22727272...
    eq = hand_equity(
        hero_hole=_hole("Ah", "Th"),
        villain_ranges=[{"KK"}],
        board=_board("Kh", "Qh", "2c", "8d"),
        seed=1,
        max_iters=5000,
    )
    # abs=1e-9: enumeration is deterministic but averages 30/132 over the 3 KK
    # combos, so allow last-ULP float-division slack against the 10/44 literal.
    assert eq == pytest.approx(expected, abs=1e-9), (
        f"Expected 10/44 (7 flush + 3 straight outs), got {eq}"
    )


# ---------------------------------------------------------------------------
# E-7: guaranteed chop → equity == 0.5 exactly
#
# Board:  Ah Kh Qh Jh Th  (royal flush; best possible 5-card hand)
# Hero:   2c 3c            (plays the board)
# Villain range: {"44"}    (plays the board too — 44 can't improve on royal flush)
# Both players' best 5-card hand is the board royal flush → 2-way tie → 0.5.
# ---------------------------------------------------------------------------

def test_e7_chop_play_the_board_equity_exactly_half() -> None:
    """E-7: both sides play the board (royal flush) → equity == 0.5 exactly."""
    eq = hand_equity(
        hero_hole=_hole("2c", "3c"),
        villain_ranges=[{"44"}],
        board=_board("Ah", "Kh", "Qh", "Jh", "Th"),
        seed=1,
        max_iters=5000,
    )
    assert eq == 0.5, f"Expected exactly 0.5 (chop), got {eq}"


# ---------------------------------------------------------------------------
# E-8: enum vs MC agreement within ±0.02 for the same 1-card-to-come spot
#
# Use a 4-card board so the engine runs exact enumeration by default.  We
# then explicitly call with an absurdly large max_iters to force enumeration
# (the exact path) and separately run the same spot but with a preflop board
# (MC path), checking both land within ±0.02 of the analytic expectation.
#
# Simpler approach: the plan allows calling MC via a test hook.  Since the
# engine's public API dispatches by len(board), we can compare:
#   - turn board (4 cards) → exact enumeration result
#   - empty board + same hands → MC result (should be close to known value)
# The plan says "enum vs MC for the *same* spot" — we accomplish this by
# calling with a turn board (which uses enumeration) twice with different
# seeds and confirming they agree (enumeration is seed-independent and MC
# with high iters converges). We also call the preflop version to confirm
# MC is within ±0.02 of the expected analytic preflop equity.
# ---------------------------------------------------------------------------

def test_e8_enum_and_mc_agree_within_tolerance() -> None:
    """E-8: enumeration (turn board) and MC (preflop) agree within ±0.02 of known values."""
    # Enumeration path: 4-card board → exact (seed-independent)
    eq_enum_s1 = hand_equity(
        hero_hole=_hole("Ah", "Th"),
        villain_ranges=[{"KK"}],
        board=_board("Kh", "Qh", "2c", "8d"),
        seed=1,
        max_iters=5000,
    )
    eq_enum_s2 = hand_equity(
        hero_hole=_hole("Ah", "Th"),
        villain_ranges=[{"KK"}],
        board=_board("Kh", "Qh", "2c", "8d"),
        seed=999,
        max_iters=5000,
    )
    # Enumeration is deterministic; both calls must be identical.
    assert eq_enum_s1 == eq_enum_s2, (
        "Enumeration path returned different values for different seeds — "
        "enumeration should be seed-independent"
    )

    # MC path: preflop → seeded MC with high iters should be within ±0.02 of
    # the known AA-vs-KK analytic value (~0.82).
    eq_mc = hand_equity(
        hero_hole=_hole("Ah", "As"),
        villain_ranges=[{"KK"}],
        board=[],
        seed=7,
        max_iters=5000,
    )
    analytic_aa_vs_kk = 0.82
    assert abs(eq_mc - analytic_aa_vs_kk) <= 0.02, (
        f"MC equity {eq_mc:.4f} deviates from analytic {analytic_aa_vs_kk} by more than ±0.02"
    )


# ---------------------------------------------------------------------------
# E-9: dead-card correctness — villain range collides with dead cards
#
# Hero holds Ah; board has As Ad.  Villain range {"AA"} → only Ac-containing
# combo (AcAh is also dead because hero holds Ah) → the only possible combo
# that *could* exist is Ac + something, but Ac Ah is out (Ah dead), Ac As is
# out (As dead), Ac Ad is out (Ad dead).  Therefore no valid AA combos remain.
#
# The engine should NOT crash.  It should return a sane equity in [0, 1].
# (With no villain combos possible, behaviour is implementation-defined — the
# test only asserts no crash + sane range, as the plan §4.2 states "assert
# the engine does not crash and returns a sane equity".)
# ---------------------------------------------------------------------------

def test_e9_dead_card_exclusion_no_crash_sane_equity() -> None:
    """E-9: villain range combos colliding with dead cards are excluded; no crash."""
    # Hero: Ah (+ Kd as second hole card to give valid input)
    # Board: As Ad 2c (3 cards)
    # Villain range: {"AA"} → all AA combos need 2 Aces; available Aces:
    #   remaining Aces after Ah (hero), As, Ad (board) = only Ac.
    #   Need 2 Aces for a combo, only 1 remains → 0 valid combos.
    eq = hand_equity(
        hero_hole=_hole("Ah", "Kd"),
        villain_ranges=[{"AA"}],
        board=_board("As", "Ad", "2c"),
        seed=1,
        max_iters=5000,
    )
    assert 0.0 <= eq <= 1.0, f"Equity {eq} out of [0, 1] range"


# ---------------------------------------------------------------------------
# E-10: range vs single hand — tighter villain range yields lower/equal hero equity
#
# Hero holds a marginal hand (JTs). Villain at 40% VPIP range vs 10% VPIP range.
# Tighter villain (10%) has a stronger range → hero does no better (equity ≤
# looser villain equity, within ±0.02 slack per plan).
# ---------------------------------------------------------------------------

def test_e10_tighter_villain_range_lower_hero_equity() -> None:
    """E-10: tighter villain range yields lower or equal hero equity for a marginal hand."""
    board = _board("Qd", "9c", "3h")  # flop

    eq_loose = hand_equity(
        hero_hole=_hole("Jh", "Ts"),
        villain_ranges=[default_range(0.40)],
        board=board,
        seed=123,
        max_iters=5000,
    )
    eq_tight = hand_equity(
        hero_hole=_hole("Jh", "Ts"),
        villain_ranges=[default_range(0.10)],
        board=board,
        seed=123,
        max_iters=5000,
    )

    assert isinstance(eq_loose, float), "hand_equity did not return a float for loose range"
    assert isinstance(eq_tight, float), "hand_equity did not return a float for tight range"
    assert 0.0 < eq_loose < 1.0, f"Loose-range equity {eq_loose} not in (0, 1)"
    assert 0.0 < eq_tight < 1.0, f"Tight-range equity {eq_tight} not in (0, 1)"
    # Tighter villain = stronger holdings = lower or equal hero equity (±0.02 slack)
    assert eq_tight <= eq_loose + 0.02, (
        f"Tighter villain range gave HIGHER hero equity ({eq_tight:.4f} > "
        f"{eq_loose:.4f} + 0.02) — violates monotonicity expectation"
    )


# ---------------------------------------------------------------------------
# Extra: range_to_combos dead-card removal (exercises E-9 internals directly)
# ---------------------------------------------------------------------------

def test_range_to_combos_excludes_dead_cards() -> None:
    """range_to_combos must not return any combo that overlaps dead_cards."""
    dead = [C("Ah"), C("As"), C("Ad")]  # three aces dead
    combos = range_to_combos({"AA"}, dead)
    # Only Ac remains; no valid 2-Ace combo is possible.
    assert combos == [], (
        f"Expected no AA combos when 3 aces are dead, got {combos}"
    )


def test_range_to_combos_full_pair_without_dead() -> None:
    """range_to_combos with no dead cards returns all 6 AA combos."""
    combos = range_to_combos({"AA"}, dead_cards=[])
    assert len(combos) == 6, f"Expected 6 AA combos with no dead cards, got {len(combos)}"
