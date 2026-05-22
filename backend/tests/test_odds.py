"""
test_odds.py — pinned dealer-bust % values for 6-deck H17 blackjack.

AC-T1 / AC-B1 / AC-B2.

Source: standard Wizard of Odds dealer-outcome table. These specific values
are part of the public contract — the Chipy prompt cites them verbatim, so
they must not drift without a deliberate change.

Every test is synchronous (dealer_bust_pct is a pure function, no I/O).
"""
from __future__ import annotations

import pytest

# This import will fail (ImportError / ModuleNotFoundError) until the
# implementer creates backend/game/blackjack/odds.py.
from backend.game.blackjack.odds import dealer_bust_pct


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _h(value: str, suit: str = "hearts") -> dict:
    """Return a minimal card dict for tidy parametrize lines."""
    return {"suit": suit, "value": value}


# ─── Pinned values (AC-B2) ───────────────────────────────────────────────────
#
# (upcard_value, expected_pct) — every face value the deck can show.

PINS: list[tuple[str, float]] = [
    ("2", 0.35),
    ("3", 0.37),
    ("4", 0.40),
    ("5", 0.42),
    ("6", 0.42),
    ("7", 0.26),
    ("8", 0.24),
    ("9", 0.23),
    ("10", 0.23),
    ("J", 0.23),
    ("Q", 0.23),
    ("K", 0.23),
    ("A", 0.17),
]


@pytest.mark.parametrize("value, expected", PINS, ids=[v for v, _ in PINS])
def test_dealer_bust_pct_pinned_value(value: str, expected: float) -> None:
    """AC-B2: every rank returns the exact pinned float."""
    assert dealer_bust_pct(_h(value, suit="spades")) == pytest.approx(expected, abs=1e-9)


# ─── Range guard (AC-B1) ─────────────────────────────────────────────────────

@pytest.mark.parametrize("value, _expected", PINS, ids=[v for v, _ in PINS])
def test_dealer_bust_pct_in_unit_range(value: str, _expected: float) -> None:
    """AC-B1: return value is always in [0.0, 1.0]."""
    pct = dealer_bust_pct(_h(value))
    assert 0.0 <= pct <= 1.0, f"dealer_bust_pct returned {pct!r} for {value!r}"


# ─── Determinism ─────────────────────────────────────────────────────────────

def test_dealer_bust_pct_is_deterministic() -> None:
    """Same input must always produce exactly the same output."""
    card = _h("6")
    assert dealer_bust_pct(card) == dealer_bust_pct(card)
    assert dealer_bust_pct(card) == dealer_bust_pct(_h("6", suit="clubs"))


# ─── Type-error guard ─────────────────────────────────────────────────────────

def test_dealer_bust_pct_unknown_value_raises() -> None:
    """Passing an unrecognised card value must raise KeyError or ValueError."""
    with pytest.raises((KeyError, ValueError)):
        dealer_bust_pct({"suit": "spades", "value": "ZZ"})
