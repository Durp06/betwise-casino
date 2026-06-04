"""backend.game.pai_gow.resolver — pure side-compare and hand-result logic.

Implements the 9-cell truth table from spec §10. Sides resolve as BINARY:
player strictly wins or doesn't (COPY = dealer wins per house rule §7.5).
The overall hand result is derived from the count of strict-player-win
sides: 2 → WIN, 1 → PUSH, 0 → LOSE.

The 3 "copy" truth-table cells (copy+copy, banker+copy, copy+banker) all
resolve to LOSE — this was the round-4 catch where an earlier draft had
side-level push state and would have incorrectly evaluated (copy, copy)
as push+push → push.

All functions are pure (no DB, no IO). Foul rule is short-circuited
BEFORE this resolver runs (per spec §9.5 step 2a) — fouled hands skip the
truth table entirely and resolve to LOSE without comparing.
"""
from __future__ import annotations

from enum import Enum


class SideCompare(str, Enum):
    """Outcome of comparing one side (front OR back) of player vs dealer.

    PLAYER  player's hand is STRICTLY higher under §7.3 unified ordering.
    BANKER  dealer's hand is STRICTLY higher.
    COPY    exact tie. Per §7.5 house rule, banker wins copies, so COPY is
            treated as "not a player win" by the truth table below.
    """
    PLAYER = "player"
    BANKER = "banker"
    COPY = "copy"


class HandResult(str, Enum):
    """Net outcome for the player on this hand."""
    WIN = "win"
    PUSH = "push"
    LOSE = "lose"


def compare_side(player_rank: tuple, banker_rank: tuple) -> SideCompare:
    """Compare one side under §7.3 unified ordering.

    Inputs are totally-ordered tuples produced by `evaluator.score_hand(...)`.
    Works for 2-card hands (shorter tuple) vs 5-card hands (longer tuple)
    because Python tuple comparison breaks prefix ties by length.
    """
    if player_rank > banker_rank:
        return SideCompare.PLAYER
    if player_rank < banker_rank:
        return SideCompare.BANKER
    return SideCompare.COPY


def resolve_hand(front: SideCompare, back: SideCompare) -> HandResult:
    """Apply the §10 truth table. Counts sides where player STRICTLY wins:
      2 → WIN, 1 → PUSH, 0 → LOSE.

    COPY counts as "not a player win" — so (COPY, COPY) → LOSE, not push.
    """
    player_wins = int(front is SideCompare.PLAYER) + int(back is SideCompare.PLAYER)
    if player_wins == 2:
        return HandResult.WIN
    if player_wins == 1:
        return HandResult.PUSH
    return HandResult.LOSE


def ante_payout_cents(result: HandResult, bet_cents: int) -> int:
    """NET delta to player's chip_balance for this ante.

    WIN  → +bet (1:1; v1 has no 5% commission per §7.6).
    PUSH → 0.
    LOSE → -bet.

    Note: this is the NET delta over the full deal→resolve cycle. The state
    machine in `state.py` handles the escrow-aware chip_balance writes
    separately (chip_balance -= bet at deal, += 2*bet on WIN at resolve,
    += bet on PUSH at resolve, nothing on LOSE) — see spec §9.5 step 3.
    The two views reconcile: -bet (escrow) + return = net delta.
    """
    if result is HandResult.WIN:
        return bet_cents
    if result is HandResult.LOSE:
        return -bet_cents
    return 0
