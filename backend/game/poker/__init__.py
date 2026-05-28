"""backend.game.poker — Texas Hold'em (educational SNG) game module.

Public surface (re-exported for `from backend.game.poker import ...`):

- cards: Suit, Rank, Card, SUITS, RANKS, create_deck, shuffle, deal
- evaluator: Category, RankedHand, rank_hand, best_5_of_7, compare
- ranges: chen_score, SKLANSKY_GROUPS, HAND_GRID, hand_str, combos_for, SC_RANK_ORDER
- pot_odds: required_equity, bluff_breakeven, mdf, equity_from_outs
- equity: equity, EquityResult
- nash: push_fold_action, PUSH_FOLD_CHART
- icm: harville_finish_distribution, icm_equity, icm_breakeven_call_equity
- archetypes: ARCHETYPE_REGISTRY, decide, ArchetypeSpec, ArchetypeDecision
- state: BettingState, apply_action, next_to_act, compute_side_pots, award_pots
- tournament: BLIND_SCHEDULE_DEFAULT, PAYOUT_STRUCTURE_BY_SEATS, current_level
- oracle: classify_decision, DecisionClassification
- prompts: build_reads_prompt, build_odds_prompt

The brain is pure-sync; no DB or network IO. Routers (async) consume these
helpers and persist results to SQLAlchemy.
"""
from __future__ import annotations

GAME_TYPE = "poker"

# Re-export submodules so `from backend.game.poker import cards, evaluator, ...`
# works without a chain of imports inside callers. The submodules are pure-sync;
# importing this package does not touch the DB or the network.
from . import cards  # noqa: F401,E402
