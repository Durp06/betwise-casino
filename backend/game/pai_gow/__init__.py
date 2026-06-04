"""backend.game.pai_gow — Pai Gow Poker (house-banked) game module.

Owner: halynk21. See `specs/pai-gow.md` for the locked spec.

Submodules (added during Phase 3 of the build):
  - cards     : Card representation, deck (52 + joker), seeded shuffle
  - evaluator : 5-card + 2-card hand strength, unified comparison protocol
  - house_way : Foxwoods house way (~20-rule table); dealer + auto-set algo
  - optimal_set : house_way + published deviation table + unit EV-per-bet table
  - fortune   : qualifying-hand detection + payout schedule (fixed + pool tiers)
  - resolver  : pure side-compare → hand_result (the 9-cell truth table)
  - canonical : hand canonicalization for Chipy cache key (rank-sort + joker token)
  - state     : async DB helpers (deal, set, auto-set on timeout, resolve)
  - prompts   : Chipy pre/post prompt templates

For routing, see `backend/routers/pai_gow_tables.py`, `pai_gow_game.py`,
`pai_gow_advice.py` (added in Phase 4).
"""
from __future__ import annotations

GAME_TYPE = "pai_gow"
