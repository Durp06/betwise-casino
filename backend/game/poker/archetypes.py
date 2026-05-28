"""
archetypes.py — bot archetype engine for Texas Hold'em.

Design constraints (specs/texas-holdem.md §AC-B28..B30, brief §4.3 landmine):
- ≥10 named archetypes per reference §12.
- Pure functions; deterministic given an RNG.
- SINGLE SOURCE OF TRUTH: `decide(spec, context, rng)` returns both the bot's
  chosen action AND the coach's read on that bot (estimated range + intent
  label). The bot-actor and the coach-explainer consume the same function.
  If a bot raises, its self-reported estimated_opponent_range MUST contain
  the hand-class the action implies. The test suite enforces this.

The decision policy is a parameterized heuristic: VPIP / PFR / aggression
factor band parameters drive open/3-bet frequencies and bet-sizing
selection. Postflop, archetypes evaluate their hand strength via a simple
Chen-style + made-hand classification (no equity engine call inside the bot
decision — keep bots fast and behavior-stable across runs).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Final, Literal

from .cards import Card
from .ranges import (
    hand_str,
    top_pct,
    union_of_groups,
)


# ─── Types ────────────────────────────────────────────────────────────────────


BotAction = Literal["fold", "check", "call", "raise", "all_in"]
Intent = Literal[
    "value",         # betting strong hand for chips
    "thin_value",    # betting a medium hand expecting worse to call
    "bluff",         # betting weak hand expecting better to fold
    "semi_bluff",    # betting drawing hand with fold equity + outs
    "trap",          # slow-playing nuts to induce
    "pot_control",   # checking a medium hand to keep pot small
    "give_up",       # checking weak hand with no future plan
    "blind_defend",  # calling out of position to defend a big blind
]


@dataclass(frozen=True)
class ArchetypeSpec:
    """Parameters defining one archetype."""

    name: str                   # e.g. "TAG", "Maniac"
    animal: str | None          # Hellmuth animal label or None
    vpip: float                 # voluntarily-put-in-pot frequency (0..1)
    pfr: float                  # preflop-raise frequency (0..1)
    af: float                   # postflop aggression factor (≥0)
    bluff_freq: float           # postflop bluff frequency on missed (0..1)
    fold_to_aggression: float   # frequency of folding to a raise (0..1)
    description: str            # coach-facing one-liner
    sizing_bb: float = 2.5      # default open size (bb), preflop


@dataclass(frozen=True)
class ArchetypeContext:
    """Inputs to decide(). Pure data."""

    hole: tuple[Card, Card]
    board: tuple[Card, ...]       # 0/3/4/5 cards
    street: Literal["preflop", "flop", "turn", "river"]
    position: str                 # SB / BB / BTN / CO / HJ / MP / UTG / ...
    stack_bb: float
    pot_bb: float
    to_call_bb: float             # 0 means it's checked to us
    n_live_opponents: int


@dataclass(frozen=True)
class ArchetypeDecision:
    """Output of decide(). The coach reads `estimated_opponent_range` to
    explain "what this bot's action means" — the single-source-of-truth
    contract from brief §4.3."""

    action: BotAction
    raise_to_bb: float          # only used when action=="raise"; 0 otherwise
    intent: Intent
    estimated_opponent_range: frozenset[str]
    coach_note: str             # human-readable read for the coach prose
    chosen_hand_class: str      # e.g. "premium_pair", "suited_broadway", "junk"


# ─── Hand classification (lightweight, postflop) ──────────────────────────────


def _hand_str_from_cards(c1: Card, c2: Card) -> str:
    return hand_str(c1["value"], c1["suit"], c2["value"], c2["suit"])


def _is_premium_starter(hand: str) -> bool:
    """SM Groups 1-2 — AA, KK, QQ, JJ, TT, AKs, AKo, AQs, AJs, KQs."""
    return hand in union_of_groups(1, 2)


def _is_strong_starter(hand: str) -> bool:
    """Groups 1-3."""
    return hand in union_of_groups(1, 2, 3)


def _is_playable_starter(hand: str) -> bool:
    """Groups 1-5 — what a tight player open-raises."""
    return hand in union_of_groups(1, 2, 3, 4, 5)


# ─── Archetype registry (≥10 per AC-B30) ──────────────────────────────────────


ARCHETYPE_REGISTRY: Final[dict[str, ArchetypeSpec]] = {
    "TAG": ArchetypeSpec(
        name="TAG",
        animal="Lion",
        vpip=0.22, pfr=0.20, af=3.0,
        bluff_freq=0.15, fold_to_aggression=0.55,
        description="Tight-aggressive. Plays strong ranges, raises not limps, c-bets often, folds to real strength.",
        sizing_bb=2.5,
    ),
    "LAG": ArchetypeSpec(
        name="LAG",
        animal=None,
        vpip=0.30, pfr=0.26, af=5.0,
        bluff_freq=0.35, fold_to_aggression=0.35,
        description="Loose-aggressive. Wide opens, 3-bet bluffs, barrels multiple streets.",
        sizing_bb=3.0,
    ),
    "Nit": ArchetypeSpec(
        name="Nit",
        animal="Mouse",
        vpip=0.12, pfr=0.10, af=1.5,
        bluff_freq=0.05, fold_to_aggression=0.75,
        description="Folds nearly everything. Only big-bets the near-nuts. Highly bluffable.",
        sizing_bb=3.0,
    ),
    "CallingStation": ArchetypeSpec(
        name="CallingStation",
        animal="Elephant",
        vpip=0.45, pfr=0.08, af=0.7,
        bluff_freq=0.02, fold_to_aggression=0.20,
        description="Calls down with anything. Impossible to bluff — value-bet thin, never bluff.",
        sizing_bb=2.0,
    ),
    "Maniac": ArchetypeSpec(
        name="Maniac",
        animal="Jackal",
        vpip=0.50, pfr=0.34, af=6.0,
        bluff_freq=0.50, fold_to_aggression=0.20,
        description="Random aggression. Distinguished from a fish by high PFR/AF.",
        sizing_bb=4.0,
    ),
    "SetMiner": ArchetypeSpec(
        name="SetMiner",
        animal="Mouse",
        vpip=0.15, pfr=0.05, af=1.5,
        bluff_freq=0.05, fold_to_aggression=0.70,
        description="Plays small pairs cheap hoping to flop a set; passive otherwise.",
        sizing_bb=2.5,
    ),
    "ABC": ArchetypeSpec(
        name="ABC",
        animal="Lion",
        vpip=0.20, pfr=0.18, af=2.5,
        bluff_freq=0.10, fold_to_aggression=0.55,
        description="Straightforward — value-bet strong, fold weak. No creativity.",
        sizing_bb=2.5,
    ),
    "TAGFish": ArchetypeSpec(
        name="TAGFish",
        animal=None,
        vpip=0.24, pfr=0.20, af=2.5,
        bluff_freq=0.15, fold_to_aggression=0.40,
        description="Looks TAG by preflop stats; leaks postflop — over-calls and auto-pilots.",
        sizing_bb=2.5,
    ),
    "Whale": ArchetypeSpec(
        name="Whale",
        animal="Elephant",
        vpip=0.55, pfr=0.08, af=0.7,
        bluff_freq=0.05, fold_to_aggression=0.15,
        description="A station who reloads. Plays everything; calls big bets without concern.",
        sizing_bb=2.0,
    ),
    "Trapper": ArchetypeSpec(
        name="Trapper",
        animal=None,
        vpip=0.22, pfr=0.14, af=1.8,
        bluff_freq=0.08, fold_to_aggression=0.45,
        description="Slow-plays monsters; flat-calls strong hands to induce. Passive line that explodes.",
        sizing_bb=2.5,
    ),
    "Shark": ArchetypeSpec(
        name="Shark",
        animal="Eagle",
        vpip=0.25, pfr=0.22, af=3.0,
        bluff_freq=0.25, fold_to_aggression=0.50,
        description="Balanced and near-unexploitable. Tells vanish — play fundamentally sound.",
        sizing_bb=2.5,
    ),
}


def list_archetype_names() -> list[str]:
    return list(ARCHETYPE_REGISTRY.keys())


# ─── Range model (single source of truth) ─────────────────────────────────────


def _opening_range(spec: ArchetypeSpec) -> set[str]:
    """Hands this archetype open-raises with from any decent position.

    Derived from PFR — the bot opens approximately PFR% of hands; the coach
    reads "this bot only raises with that range" against the same set.
    """
    pct_to_open = spec.pfr * 100.0
    return top_pct(pct_to_open)


def _calling_range(spec: ArchetypeSpec) -> set[str]:
    """Hands this archetype call-only with (the limp/call set).

    The full VPIP set is (PFR opens) + (call-only set); call-only = VPIP - PFR.
    """
    vpip_pct = spec.vpip * 100.0
    pfr_pct = spec.pfr * 100.0
    if vpip_pct <= pfr_pct:
        return set()
    full = top_pct(vpip_pct)
    opens = top_pct(pfr_pct)
    return full - opens


def _all_play_range(spec: ArchetypeSpec) -> set[str]:
    """Union of opens + calls — full VPIP."""
    return _opening_range(spec) | _calling_range(spec)


# ─── Decision policy ─────────────────────────────────────────────────────────


def _preflop_decision(
    spec: ArchetypeSpec,
    ctx: ArchetypeContext,
    rng: random.Random,
) -> ArchetypeDecision:
    hand = _hand_str_from_cards(ctx.hole[0], ctx.hole[1])
    open_range = _opening_range(spec)
    call_range = _calling_range(spec)

    # ≤15bb stacks lean into push/fold via the Nash module; archetypes follow
    # those guidelines too. Short stacks shove with strong hands.
    if ctx.stack_bb <= 12 and _is_premium_starter(hand):
        return ArchetypeDecision(
            action="all_in",
            raise_to_bb=ctx.stack_bb,
            intent="value",
            estimated_opponent_range=frozenset(union_of_groups(1, 2)),
            coach_note="Short stack jam with a premium hand — standard ICM-aware shove.",
            chosen_hand_class="premium",
        )

    facing_bet = ctx.to_call_bb > 0
    if facing_bet:
        # Facing a raise. Re-raise with premium; call with strong-but-not-3-bettable;
        # fold otherwise. Maniacs/LAGs 3-bet wider; Nits/SetMiners never 3-bet bluff.
        if _is_premium_starter(hand) and rng.random() > spec.fold_to_aggression * 0.2:
            return ArchetypeDecision(
                action="raise",
                raise_to_bb=ctx.to_call_bb * 3.0,
                intent="value",
                estimated_opponent_range=frozenset(open_range),
                coach_note=f"{spec.name} 3-bets a premium against an open.",
                chosen_hand_class="premium",
            )
        if _is_playable_starter(hand) and rng.random() > spec.fold_to_aggression:
            return ArchetypeDecision(
                action="call",
                raise_to_bb=0.0,
                intent="blind_defend" if ctx.position == "BB" else "value",
                estimated_opponent_range=frozenset(open_range),
                coach_note=f"{spec.name} flat-calls in position with a playable hand.",
                chosen_hand_class="playable",
            )
        return ArchetypeDecision(
            action="fold",
            raise_to_bb=0.0,
            intent="give_up",
            estimated_opponent_range=frozenset(open_range),
            coach_note=f"{spec.name} folds — hand below their continuing range.",
            chosen_hand_class="junk",
        )

    # Open the action — no one has raised yet.
    if hand in open_range:
        # Maniac sometimes goes for the all-in shove preflop
        if spec.name == "Maniac" and ctx.stack_bb <= 20 and rng.random() < 0.3:
            return ArchetypeDecision(
                action="all_in",
                raise_to_bb=ctx.stack_bb,
                intent="bluff",
                estimated_opponent_range=frozenset(open_range),
                coach_note="Maniac shoves preflop — could be any of their opening range.",
                chosen_hand_class="any",
            )
        return ArchetypeDecision(
            action="raise",
            raise_to_bb=spec.sizing_bb,
            intent="value" if _is_strong_starter(hand) else "thin_value",
            estimated_opponent_range=frozenset(open_range),
            coach_note=f"{spec.name} opens — their PFR range is ~{int(spec.pfr * 100)}% of hands.",
            chosen_hand_class="opening",
        )
    if hand in call_range:
        return ArchetypeDecision(
            action="call",
            raise_to_bb=0.0,
            intent="value",
            estimated_opponent_range=frozenset(_all_play_range(spec)),
            coach_note=f"{spec.name} limps — their VPIP-PFR gap is non-trivial.",
            chosen_hand_class="speculative",
        )
    if ctx.to_call_bb == 0.0 and ctx.position == "BB":
        # Free check in the big blind
        return ArchetypeDecision(
            action="check",
            raise_to_bb=0.0,
            intent="blind_defend",
            estimated_opponent_range=frozenset(),
            coach_note="BB checks for free.",
            chosen_hand_class="any",
        )
    return ArchetypeDecision(
        action="fold",
        raise_to_bb=0.0,
        intent="give_up",
        estimated_opponent_range=frozenset(_all_play_range(spec)),
        coach_note=f"{spec.name} folds — below VPIP threshold.",
        chosen_hand_class="junk",
    )


def _postflop_decision(
    spec: ArchetypeSpec,
    ctx: ArchetypeContext,
    rng: random.Random,
) -> ArchetypeDecision:
    """Heuristic postflop policy based on hand strength + archetype params."""
    # Lightweight hand strength: Chen-ish + made-hand bias on the flop.
    from .evaluator import best_5_of_7, Category  # noqa: PLC0415

    rank = best_5_of_7(list(ctx.hole) + list(ctx.board))
    strong = rank.category >= Category.TRIPS  # trips or better → strong
    medium = rank.category in (Category.TWO_PAIR, Category.PAIR)  # made hand
    weak = rank.category == Category.HIGH_CARD

    facing_bet = ctx.to_call_bb > 0
    pot_odds = ctx.to_call_bb / (ctx.pot_bb + ctx.to_call_bb) if facing_bet else 0.0

    if facing_bet:
        # Calling station calls almost anything
        if spec.name == "CallingStation" or spec.name == "Whale":
            if pot_odds < 0.45:
                return ArchetypeDecision(
                    action="call",
                    raise_to_bb=0.0,
                    intent="value" if strong or medium else "blind_defend",
                    estimated_opponent_range=top_pct(40) | {"AA", "KK"},
                    coach_note=f"{spec.name} calls — they call too wide; value-bet thin against them.",
                    chosen_hand_class="any",
                )
            return _fold(spec, "to_oversize")

        # Strong hand → raise (or call for trap)
        if strong:
            if spec.name == "Trapper" and rng.random() < 0.6:
                return ArchetypeDecision(
                    action="call",
                    raise_to_bb=0.0,
                    intent="trap",
                    estimated_opponent_range=top_pct(20),
                    coach_note="Trapper slow-plays a monster — passive line that's about to explode.",
                    chosen_hand_class="monster",
                )
            return ArchetypeDecision(
                action="raise",
                raise_to_bb=ctx.to_call_bb * 3.0,
                intent="value",
                estimated_opponent_range=top_pct(30),
                coach_note=f"{spec.name} raises with a strong made hand.",
                chosen_hand_class="strong",
            )

        # Medium hand → call if pot odds work
        if medium and pot_odds < 0.35:
            return ArchetypeDecision(
                action="call",
                raise_to_bb=0.0,
                intent="value",
                estimated_opponent_range=top_pct(30),
                coach_note=f"{spec.name} calls with a medium hand — pot odds support it.",
                chosen_hand_class="medium",
            )

        # Weak hand vs aggression — Nit/Mouse folds; Maniac/LAG sometimes calls/raises
        if weak and rng.random() < spec.fold_to_aggression:
            return _fold(spec, "to_aggression")
        if weak and spec.name in ("Maniac", "LAG") and rng.random() < spec.bluff_freq:
            return ArchetypeDecision(
                action="raise",
                raise_to_bb=ctx.to_call_bb * 2.5,
                intent="bluff",
                estimated_opponent_range=top_pct(40),
                coach_note=f"{spec.name} raises wide — this is often a bluff.",
                chosen_hand_class="any",
            )
        return _fold(spec, "marginal")

    # Action is checked to us — decide to bet or check
    if strong:
        # Trap occasionally
        if spec.name == "Trapper" and rng.random() < 0.5:
            return ArchetypeDecision(
                action="check",
                raise_to_bb=0.0,
                intent="trap",
                estimated_opponent_range=top_pct(25),
                coach_note="Trapper checks with strength — induce.",
                chosen_hand_class="monster",
            )
        return ArchetypeDecision(
            action="raise",
            raise_to_bb=max(2.0, ctx.pot_bb * 0.66),
            intent="value",
            estimated_opponent_range=top_pct(30),
            coach_note=f"{spec.name} value-bets a strong made hand.",
            chosen_hand_class="strong",
        )
    if medium:
        # ABC / TAG bet for thin value; Nit checks
        if spec.name in ("Nit", "SetMiner"):
            return ArchetypeDecision(
                action="check",
                raise_to_bb=0.0,
                intent="pot_control",
                estimated_opponent_range=top_pct(30),
                coach_note=f"{spec.name} pot-controls a medium hand.",
                chosen_hand_class="medium",
            )
        return ArchetypeDecision(
            action="raise",
            raise_to_bb=max(2.0, ctx.pot_bb * 0.5),
            intent="thin_value",
            estimated_opponent_range=top_pct(35),
            coach_note=f"{spec.name} bets for thin value.",
            chosen_hand_class="medium",
        )
    # Weak — bluff per archetype frequency
    if rng.random() < spec.bluff_freq:
        return ArchetypeDecision(
            action="raise",
            raise_to_bb=max(2.0, ctx.pot_bb * 0.66),
            intent="bluff",
            estimated_opponent_range=top_pct(45),
            coach_note=f"{spec.name} bets — could be a bluff given their style.",
            chosen_hand_class="any",
        )
    return ArchetypeDecision(
        action="check",
        raise_to_bb=0.0,
        intent="give_up",
        estimated_opponent_range=top_pct(45),
        coach_note=f"{spec.name} gives up — checks back.",
        chosen_hand_class="weak",
    )


def _fold(spec: ArchetypeSpec, reason: str) -> ArchetypeDecision:
    return ArchetypeDecision(
        action="fold",
        raise_to_bb=0.0,
        intent="give_up",
        estimated_opponent_range=top_pct(30),
        coach_note=f"{spec.name} folds ({reason}).",
        chosen_hand_class="junk",
    )


def decide(spec: ArchetypeSpec, ctx: ArchetypeContext, rng: random.Random) -> ArchetypeDecision:
    """The single source of truth — bot's action + coach's read.

    The same function is called by the bot-actor (server resolves the bot's
    decision) and the coach-explainer (which builds the prompt fed to Chipy).
    They cannot disagree because they consume the same return value.
    """
    if ctx.street == "preflop":
        return _preflop_decision(spec, ctx, rng)
    return _postflop_decision(spec, ctx, rng)


# ─── Random archetype assignment (table creation) ─────────────────────────────


def assign_random_archetypes(
    n_bots: int,
    rng: random.Random | None = None,
    guarantee_variety: bool = False,
) -> list[ArchetypeSpec]:
    """Assign random archetypes for `n_bots` bot seats.

    Brief mandate: random by default. `guarantee_variety=True` avoids drawing
    the same archetype more than once if the registry has enough entries.
    """
    if rng is None:
        rng = random.Random()
    names = list(ARCHETYPE_REGISTRY.keys())
    if guarantee_variety and n_bots <= len(names):
        chosen = rng.sample(names, n_bots)
    else:
        chosen = [rng.choice(names) for _ in range(n_bots)]
    return [ARCHETYPE_REGISTRY[name] for name in chosen]


__all__ = [
    "BotAction",
    "Intent",
    "ArchetypeSpec",
    "ArchetypeContext",
    "ArchetypeDecision",
    "ARCHETYPE_REGISTRY",
    "list_archetype_names",
    "decide",
    "assign_random_archetypes",
]
