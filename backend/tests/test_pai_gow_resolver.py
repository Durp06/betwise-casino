"""
test_pai_gow_resolver.py — unit tests for the §10 truth table.

The 3 "copy" cells (copy+copy, banker+copy, copy+banker) are MANDATORY and
non-negotiable per the round-4 review — these are the exact cells where an
earlier draft of the spec (with side-level push) would have evaluated
(copy, copy) as push+push → push, incorrectly refunding the player when the
dealer should have won.
"""
from __future__ import annotations

from backend.game.pai_gow.resolver import (
    HandResult,
    SideCompare,
    ante_payout_cents,
    compare_side,
    resolve_hand,
)


# ─── compare_side ────────────────────────────────────────────────────────────


def test_compare_side_player_higher_returns_player():
    assert compare_side((4, 10), (4, 8)) is SideCompare.PLAYER


def test_compare_side_banker_higher_returns_banker():
    assert compare_side((4, 8), (4, 10)) is SideCompare.BANKER


def test_compare_side_tied_returns_copy():
    """Equal score tuples → COPY (dealer wins per house rule §7.5)."""
    assert compare_side((1, 13, 12, 9, 5), (1, 13, 12, 9, 5)) is SideCompare.COPY


def test_compare_side_works_on_variable_length_tuples():
    """2-card score (length 2 or 3) vs 5-card score (length 5 or 6) — the
    unified-ordering protocol from §7.3 just uses tuple comparison."""
    two_card_pair_k = (1, 13)
    five_card_pair_k_with_kickers = (1, 13, 12, 9, 5)
    # 5-card pair-K-with-kickers > 2-card pair-K (kickers tip the comparison)
    assert compare_side(five_card_pair_k_with_kickers, two_card_pair_k) is SideCompare.PLAYER


# ─── 9-cell truth table (spec §10 — VERBATIM) ────────────────────────────────


def test_truth_player_player_is_WIN():
    """(player, player) — 2 strict wins → WIN."""
    assert resolve_hand(SideCompare.PLAYER, SideCompare.PLAYER) is HandResult.WIN


def test_truth_player_banker_is_PUSH():
    """(player, banker) — 1 strict win → PUSH."""
    assert resolve_hand(SideCompare.PLAYER, SideCompare.BANKER) is HandResult.PUSH


def test_truth_player_copy_is_PUSH():
    """(player, copy) — copy is NOT a player win → 1 strict win → PUSH."""
    assert resolve_hand(SideCompare.PLAYER, SideCompare.COPY) is HandResult.PUSH


def test_truth_banker_player_is_PUSH():
    """(banker, player) — 1 strict win → PUSH."""
    assert resolve_hand(SideCompare.BANKER, SideCompare.PLAYER) is HandResult.PUSH


def test_truth_banker_banker_is_LOSE():
    """(banker, banker) — 0 strict wins → LOSE."""
    assert resolve_hand(SideCompare.BANKER, SideCompare.BANKER) is HandResult.LOSE


def test_truth_banker_copy_is_LOSE_round4_catch():
    """(banker, copy) — 0 strict wins → LOSE.

    Round-4 catch: an earlier draft would have treated copy as push, giving
    push+lose = push, incorrectly refunding the player.
    """
    assert resolve_hand(SideCompare.BANKER, SideCompare.COPY) is HandResult.LOSE


def test_truth_copy_player_is_PUSH():
    """(copy, player) — 1 strict win → PUSH."""
    assert resolve_hand(SideCompare.COPY, SideCompare.PLAYER) is HandResult.PUSH


def test_truth_copy_banker_is_LOSE_round4_catch():
    """(copy, banker) — 0 strict wins → LOSE. Round-4 catch."""
    assert resolve_hand(SideCompare.COPY, SideCompare.BANKER) is HandResult.LOSE


def test_truth_copy_copy_is_LOSE_round4_headline():
    """(copy, copy) — 0 strict wins → LOSE.

    THE round-4 headline catch. With the earlier push-at-side-level model,
    this would have been push+push → push, refunding the player on a hand
    where the dealer ties on BOTH sides and the house rule says dealer wins
    both copies. The corrected model counts STRICT player wins only.
    """
    assert resolve_hand(SideCompare.COPY, SideCompare.COPY) is HandResult.LOSE


# ─── ante_payout_cents (net-delta-to-chip-balance contract) ──────────────────


def test_ante_payout_win_returns_positive_bet():
    """WIN → +bet (1:1 even money; v1 has no 5% commission per §7.6)."""
    assert ante_payout_cents(HandResult.WIN, 1000) == 1000


def test_ante_payout_push_returns_zero():
    """PUSH → 0 net delta. Escrowed bet is refunded by state.py separately."""
    assert ante_payout_cents(HandResult.PUSH, 1000) == 0


def test_ante_payout_lose_returns_negative_bet():
    """LOSE → -bet (escrow stays with the house)."""
    assert ante_payout_cents(HandResult.LOSE, 1000) == -1000


def test_ante_payout_scales_with_bet():
    assert ante_payout_cents(HandResult.WIN, 50_000) == 50_000
    assert ante_payout_cents(HandResult.LOSE, 50_000) == -50_000


def test_ante_payout_zero_bet_is_safe():
    """Edge case — 0-cent bet (won't occur given bet_cents > 0 CHECK, but
    defensive)."""
    assert ante_payout_cents(HandResult.WIN, 0) == 0
    assert ante_payout_cents(HandResult.PUSH, 0) == 0
    assert ante_payout_cents(HandResult.LOSE, 0) == 0
