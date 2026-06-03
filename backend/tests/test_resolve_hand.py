"""
test_resolve_hand.py — T5 (M3) Dealer natural blackjack pushes player 3-card 21.

Pure-function unit tests on `backend.game.blackjack.state.resolve_hand`.
No DB, no fixtures — just call the function directly.

AC-5.1: player 3-card 21 (9+5+7) vs dealer natural [A,K] → ("loss", 0).
        (Currently returns ("push", bet) — the bug.)
AC-5.2: player natural [A,K] vs dealer natural [A,K] → ("push", bet).
        (Two-natural push must still hold.)
AC-5.3: player 20 ([10,10]) vs dealer non-natural 20 ([10,5,5]) → ("push", bet).
        (Equal non-natural totals still push; the new branch must not over-fire.)

These tests FAIL until `resolve_hand` is fixed to insert the dealer-natural
branch before the generic value-compare path.
"""
from __future__ import annotations


# ─── Card helpers ─────────────────────────────────────────────────────────────

def _c(value: str, suit: str = "hearts") -> dict:
    return {"suit": suit, "value": value}


# ─── AC-5.1 — 3-card 21 vs dealer natural → loss ─────────────────────────────

def test_three_card_21_loses_to_dealer_natural():
    """AC-5.1: player [9,5,7] (3-card 21) vs dealer [A,K] (natural) must be
    ('loss', 0).  Before the fix, resolve_hand incorrectly returns ('push', bet)
    because it only checks player value == dealer value without first gating on
    dealer blackjack.
    """
    from backend.game.blackjack.state import resolve_hand  # noqa: PLC0415

    bet = 1_000
    hand = {
        "cards": [_c("9"), _c("5"), _c("7")],
        "bet": bet,
        "status": "active",
    }
    dealer_cards = [_c("A", "spades"), _c("K", "clubs")]

    outcome, payout = resolve_hand(hand, dealer_cards)

    assert outcome == "loss", (
        f"3-card 21 vs dealer natural must be 'loss'; got outcome={outcome!r}. "
        "Dealer natural beats any non-natural 21 — including a 3-card total of 21."
    )
    assert payout == 0, (
        f"3-card 21 vs dealer natural must pay 0; got payout={payout}"
    )


# ─── AC-5.2 — player natural vs dealer natural → push ────────────────────────

def test_player_natural_vs_dealer_natural_is_push():
    """AC-5.2: both player [A,K] and dealer [A,K] are naturals → ('push', bet).
    The existing two-natural-push behaviour must not be broken by the new branch.
    """
    from backend.game.blackjack.state import resolve_hand  # noqa: PLC0415

    bet = 2_000
    hand = {
        "cards": [_c("A"), _c("K", "spades")],
        "bet": bet,
        "status": "blackjack",
    }
    dealer_cards = [_c("A", "diamonds"), _c("Q", "clubs")]

    outcome, payout = resolve_hand(hand, dealer_cards)

    assert outcome == "push", (
        f"Player natural vs dealer natural must be 'push'; got outcome={outcome!r}"
    )
    assert payout == bet, (
        f"Push must return the original bet={bet}; got payout={payout}"
    )


# ─── AC-5.3 — non-natural equal totals still push (no over-fire) ─────────────

def test_equal_non_natural_totals_push_when_dealer_not_natural():
    """AC-5.3: player 20 ([10,10]) vs dealer non-natural 20 ([10,5,5]) → ('push', bet).
    The new dealer-natural branch must only fire when the dealer actually has a natural;
    non-natural equal totals must still resolve as a push.
    """
    from backend.game.blackjack.state import resolve_hand  # noqa: PLC0415

    bet = 500
    hand = {
        "cards": [_c("10"), _c("10", "spades")],
        "bet": bet,
        "status": "active",
    }
    dealer_cards = [_c("10", "diamonds"), _c("5", "clubs"), _c("5", "hearts")]

    outcome, payout = resolve_hand(hand, dealer_cards)

    assert outcome == "push", (
        f"Non-natural equal totals (20 vs 20) must be 'push'; got outcome={outcome!r}. "
        "The new dealer-natural branch must not fire for a 3-card dealer total of 20."
    )
    assert payout == bet, (
        f"Push must return bet={bet}; got payout={payout}"
    )
