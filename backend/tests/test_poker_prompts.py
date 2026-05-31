"""
test_poker_prompts.py — covers AC-B44, AC-B45 from specs/texas-holdem.md.
"""
from __future__ import annotations

from backend.game.poker.archetypes import ARCHETYPE_REGISTRY
from backend.game.poker.cards import parse_card
from backend.game.poker.oracle import DecisionSnapshot
from backend.game.poker.prompts import build_odds_prompt, build_reads_prompt


def C(s):
    return parse_card(s)


def _deep_snap():
    return DecisionSnapshot(
        hole=(C("As"), C("Ks")),
        board=(C("Qd"), C("Jc"), C("7h")),
        street="flop",
        position="BTN",
        hand_str="AKs",
        stack_bb=100.0,
        pot_bb=10.0,
        to_call_bb=5.0,
        n_live_opponents=2,
        seats_remaining=8,
        is_bubble=False,
        live_equity=0.45,
    )


def _short_snap():
    return DecisionSnapshot(
        hole=(C("As"), C("Ah")),
        board=(),
        street="preflop",
        position="SB",
        hand_str="AA",
        stack_bb=10.0,
        pot_bb=1.5,
        to_call_bb=0.5,
        n_live_opponents=1,
        seats_remaining=2,
        is_bubble=False,
        live_equity=None,
    )


# ─── Odds mode (AC-B44) ──────────────────────────────────────────────────────


def test_odds_prompt_deep_postflop_mentions_heuristic_or_principle() -> None:
    snap = _deep_snap()
    system, user = build_odds_prompt(snap)
    combined = (system + "\n" + user).lower()
    assert "heuristic" in combined or "principle" in combined


def test_odds_prompt_short_stack_says_deterministic() -> None:
    snap = _short_snap()
    system, user = build_odds_prompt(snap)
    combined = (system + "\n" + user).lower()
    assert "deterministic" in combined


def test_odds_prompt_includes_pot_and_stack() -> None:
    snap = _deep_snap()
    _, user = build_odds_prompt(snap)
    assert "10" in user  # pot
    assert "100" in user  # stack


def test_odds_prompt_no_archetype_names_leak() -> None:
    """Odds mode must NOT name archetypes — that's Reads mode's job."""
    snap = _deep_snap()
    system, user = build_odds_prompt(snap)
    combined = (system + "\n" + user)
    for name in ARCHETYPE_REGISTRY.keys():
        assert name not in combined or name.lower() in ("tag", "lag")  # acronyms ok


# ─── Reads mode (AC-B45) ─────────────────────────────────────────────────────


def test_reads_prompt_names_archetypes_present_at_table() -> None:
    snap = _deep_snap()
    archetypes_by_seat = {
        1: ARCHETYPE_REGISTRY["Nit"],
        2: ARCHETYPE_REGISTRY["CallingStation"],
    }
    _, user = build_reads_prompt(snap, archetypes_by_seat)
    assert "Nit" in user
    assert "CallingStation" in user


def test_reads_prompt_includes_archetype_description() -> None:
    snap = _deep_snap()
    archetypes_by_seat = {
        1: ARCHETYPE_REGISTRY["Maniac"],
    }
    _, user = build_reads_prompt(snap, archetypes_by_seat)
    assert "Random aggression" in user or "Maniac" in user


def test_reads_prompt_mode_signal_in_system() -> None:
    snap = _deep_snap()
    system, _ = build_reads_prompt(snap, {})
    assert "READS" in system


def test_reads_prompt_can_include_last_actions() -> None:
    snap = _deep_snap()
    archetypes_by_seat = {1: ARCHETYPE_REGISTRY["TAG"]}
    last_actions = {1: "raise"}
    _, user = build_reads_prompt(snap, archetypes_by_seat, last_actions)
    assert "raise" in user
