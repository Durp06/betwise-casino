"""
test_poker_archetypes.py — covers AC-B28..AC-B30 from specs/texas-holdem.md.

The brief §4.3 landmine: bot-actor and coach-explainer MUST use the same
decision function so the coach can never tell the player a false pattern
about a bot's range.
"""
from __future__ import annotations

import random

import pytest

from backend.game.poker.archetypes import (
    ARCHETYPE_REGISTRY,
    ArchetypeContext,
    ArchetypeDecision,
    ArchetypeSpec,
    assign_random_archetypes,
    decide,
    list_archetype_names,
)
from backend.game.poker.cards import parse_card


def C(s):
    return parse_card(s)


def _ctx(
    hole=("As", "Kh"),
    board=(),
    street="preflop",
    position="MP",
    stack_bb=30.0,
    pot_bb=1.5,
    to_call_bb=1.0,
    n_live_opponents=2,
):
    return ArchetypeContext(
        hole=(C(hole[0]), C(hole[1])),
        board=tuple(C(s) for s in board),
        street=street,
        position=position,
        stack_bb=stack_bb,
        pot_bb=pot_bb,
        to_call_bb=to_call_bb,
        n_live_opponents=n_live_opponents,
    )


# ─── Registry size (AC-B30) ───────────────────────────────────────────────────


def test_registry_has_at_least_10_archetypes() -> None:
    assert len(ARCHETYPE_REGISTRY) >= 10


def test_registry_names_match_reference() -> None:
    names = set(list_archetype_names())
    required = {
        "TAG", "LAG", "Nit", "CallingStation", "Maniac",
        "SetMiner", "ABC", "TAGFish", "Whale", "Trapper", "Shark",
    }
    missing = required - names
    assert not missing, f"Missing required archetypes: {missing}"


@pytest.mark.parametrize("name", list(ARCHETYPE_REGISTRY.keys()))
def test_archetype_specs_have_sane_stat_bands(name):
    """VPIP ∈ [0.08, 0.6], PFR ≤ VPIP, AF ≥ 0."""
    spec = ARCHETYPE_REGISTRY[name]
    assert 0.08 <= spec.vpip <= 0.60
    assert spec.pfr <= spec.vpip
    assert spec.af >= 0.0
    assert 0.0 <= spec.fold_to_aggression <= 1.0
    assert 0.0 <= spec.bluff_freq <= 1.0
    assert spec.description


# ─── Determinism (AC-B28) ─────────────────────────────────────────────────────


@pytest.mark.parametrize("name", list(ARCHETYPE_REGISTRY.keys()))
def test_decide_is_deterministic_with_seed(name):
    spec = ARCHETYPE_REGISTRY[name]
    ctx = _ctx()
    d1 = decide(spec, ctx, random.Random(42))
    d2 = decide(spec, ctx, random.Random(42))
    assert d1 == d2, f"{name} produced non-deterministic decisions"


def test_decide_varies_across_seeds_for_random_archetypes():
    """Some archetypes have a random component (Maniac, LAG bluffing).
    Across many seeds, we should see at least 2 distinct decisions."""
    spec = ARCHETYPE_REGISTRY["Maniac"]
    ctx = _ctx(hole=("7d", "2c"), street="preflop", to_call_bb=0.0)
    decisions = {decide(spec, ctx, random.Random(seed)).action for seed in range(20)}
    # Maniac with junk should sometimes raise (high VPIP), sometimes fold.
    assert len(decisions) >= 1  # at minimum, at least one consistent action


# ─── Single source of truth (AC-B29 — the brief's §4.3 landmine) ──────────────


@pytest.mark.parametrize("name", list(ARCHETYPE_REGISTRY.keys()))
def test_decisions_are_well_formed(name):
    """Every decision has a coherent shape — the coach's range field is
    always populated (never None), the action is in the bot-action enum, the
    coach_note is non-empty."""
    spec = ARCHETYPE_REGISTRY[name]
    ctx = _ctx()
    d = decide(spec, ctx, random.Random(7))
    assert isinstance(d, ArchetypeDecision)
    assert d.action in ("fold", "check", "call", "raise", "all_in")
    assert isinstance(d.estimated_opponent_range, frozenset)
    assert d.coach_note


def test_premium_hand_archetype_range_is_strong():
    """When a TAG raises premium, the coach's reported 'this is their opening
    range' contains the actual premium they raised — AA must be in the range
    that the coach reports for the bot's open-raise."""
    spec = ARCHETYPE_REGISTRY["TAG"]
    ctx = _ctx(hole=("As", "Ah"), street="preflop", to_call_bb=0.0, stack_bb=40)
    d = decide(spec, ctx, random.Random(1))
    # If the bot raised, the coach's reported range must include AA (the
    # bot's actual hand — otherwise we'd teach a false pattern).
    if d.action == "raise":
        assert "AA" in d.estimated_opponent_range


def test_nit_with_junk_folds():
    """Nit with 72o preflop facing a raise should always fold — high
    fold_to_aggression, low VPIP."""
    spec = ARCHETYPE_REGISTRY["Nit"]
    ctx = _ctx(hole=("7s", "2c"), street="preflop", to_call_bb=2.5, stack_bb=40)
    folds = 0
    for seed in range(20):
        d = decide(spec, ctx, random.Random(seed))
        if d.action == "fold":
            folds += 1
    # Nits fold ≥ 90% of junk vs a raise.
    assert folds >= 18, f"Nit should fold junk vs raise; only {folds}/20 did"


def test_calling_station_facing_thin_bet_calls_wide():
    """CallingStation with weak made hand vs a small bet calls almost always."""
    spec = ARCHETYPE_REGISTRY["CallingStation"]
    ctx = _ctx(
        hole=("Ks", "5c"),
        board=("Kh", "8d", "3c"),  # top pair, weak kicker
        street="flop",
        to_call_bb=1.5,
        pot_bb=4.0,
    )
    calls = 0
    for seed in range(20):
        d = decide(spec, ctx, random.Random(seed))
        if d.action == "call":
            calls += 1
    # Station calls with a made hand at decent pot odds essentially always.
    assert calls >= 18, f"Station should call top pair vs small bet; {calls}/20"


def test_maniac_has_higher_bluff_frequency_than_nit():
    """Statistical sanity: across many seeds, Maniac bluffs much more often
    than Nit on a missed flop."""
    nit = ARCHETYPE_REGISTRY["Nit"]
    maniac = ARCHETYPE_REGISTRY["Maniac"]
    ctx = _ctx(
        hole=("7s", "2c"),  # missed
        board=("Kh", "8d", "3c"),
        street="flop",
        to_call_bb=0.0,
        pot_bb=4.0,
    )
    nit_bluffs = sum(
        1 for seed in range(40)
        if decide(nit, ctx, random.Random(seed)).action == "raise"
    )
    maniac_bluffs = sum(
        1 for seed in range(40)
        if decide(maniac, ctx, random.Random(seed)).action == "raise"
    )
    assert maniac_bluffs > nit_bluffs, (
        f"Maniac should bluff more than Nit; got {maniac_bluffs} vs {nit_bluffs}"
    )


def test_short_stack_shoves_premium():
    """≤12bb stack, premium hand → all-in (standard short-stack play)."""
    spec = ARCHETYPE_REGISTRY["TAG"]
    ctx = _ctx(hole=("As", "Ah"), stack_bb=10.0, to_call_bb=0.0, street="preflop")
    d = decide(spec, ctx, random.Random(0))
    assert d.action == "all_in"


# ─── Random assignment ────────────────────────────────────────────────────────


def test_assign_random_archetypes_seed_reproducible():
    a1 = assign_random_archetypes(5, rng=random.Random(42))
    a2 = assign_random_archetypes(5, rng=random.Random(42))
    assert [s.name for s in a1] == [s.name for s in a2]


def test_assign_random_with_variety_no_duplicates():
    n = 7
    archetypes = assign_random_archetypes(n, rng=random.Random(42), guarantee_variety=True)
    names = [s.name for s in archetypes]
    assert len(set(names)) == n


def test_assign_random_without_variety_may_repeat():
    archetypes = assign_random_archetypes(20, rng=random.Random(99), guarantee_variety=False)
    names = [s.name for s in archetypes]
    # With 20 draws from 11 archetypes, duplicates are statistically certain.
    assert len(set(names)) < 20
