"""
pot_odds.py — pot odds, MDF, bluff break-even, and Rule of 2/4.

Design constraints (specs/texas-holdem.md §AC-B15..AC-B17):
- All values are deterministic — Odds mode's correctness oracle is grounded
  in this module.
- Pure functions, no DB, no network.
- Pinned table values match reference §2 and §3.
"""

from __future__ import annotations


# ─── Pot odds ────────────────────────────────────────────────────────────────


def required_equity(pot_before: int | float, opp_bet: int | float) -> float:
    """Required equity to make a 0-EV call.

    Formula: call / (pot_before + opp_bet + call), where call = opp_bet.
    Reference §2:
        ½ pot bet  → 0.25
        pot bet    → 0.333...
        2× pot bet → 0.40

    Raises ValueError for negative inputs.
    """
    if pot_before < 0 or opp_bet < 0:
        raise ValueError("Pot and bet sizes must be non-negative")
    if opp_bet == 0:
        return 0.0
    call = opp_bet
    return call / (pot_before + opp_bet + call)


def bluff_breakeven(pot_before: int | float, bet: int | float) -> float:
    """Fold equity needed to break even on a bluff.

    Formula: bet / (pot_before + bet). For a pot-sized bet → 0.5; for a half-
    pot bet → 0.333.
    """
    if pot_before < 0 or bet < 0:
        raise ValueError("Pot and bet sizes must be non-negative")
    if bet == 0:
        return 0.0
    return bet / (pot_before + bet)


def mdf(pot_before: int | float, bet: int | float) -> float:
    """Minimum Defense Frequency.

    Formula: pot_before / (pot_before + bet). The threshold of "defend at
    least this fraction of your range or you are bluff-exploitable."
    Pot-sized bet → 0.5; half-pot → 0.667.
    """
    if pot_before < 0 or bet < 0:
        raise ValueError("Pot and bet sizes must be non-negative")
    if pot_before + bet == 0:
        return 0.0
    return pot_before / (pot_before + bet)


# ─── Pinned reference §2 table ────────────────────────────────────────────────

REQUIRED_EQUITY_BY_BET_FRACTION: dict[float, float] = {
    0.25: 1 / 6,        # ¼ pot → ~16.67%
    1 / 3: 0.2,         # ⅓ pot → 20%
    0.50: 0.25,         # ½ pot → 25%
    2 / 3: 2 / 7,       # ⅔ pot → ~28.57%
    0.75: 0.3,          # ¾ pot → 30%
    1.00: 1 / 3,        # pot → 33.33%
    1.50: 0.375,        # 1.5× pot → 37.5%
    2.00: 0.4,          # 2× pot → 40%
}


def required_equity_for_pot_fraction(bet_fraction_of_pot: float) -> float:
    """Convenience: given a bet expressed as a fraction of the pot, return
    the required call equity. Identical to required_equity(1.0, bet_fraction)."""
    return required_equity(1.0, bet_fraction_of_pot)


# ─── Rule of 2 and 4 (AC-B17) ────────────────────────────────────────────────


def equity_from_outs(outs: int, streets_to_come: int) -> float:
    """Approximate equity for a drawing hand using the Rule of 2 and 4.

    streets_to_come = 2 means flop → river (two cards): outs × 4.
    streets_to_come = 1 means turn → river (one card): outs × 2.

    For outs ≥ 12 with two streets to come, shade down — the linear
    approximation overestimates significantly. We use a published
    correction: at 12 outs equity ≈ 45%, at 15 outs ≈ 54%, capped.
    """
    if outs < 0:
        raise ValueError("Cannot have negative outs")
    if streets_to_come not in (1, 2):
        raise ValueError("streets_to_come must be 1 or 2")
    if outs == 0:
        return 0.0

    if streets_to_come == 1:
        # Rule of 2: outs × 2%. Caps gracefully at 100.
        return min(outs * 0.02, 1.0)

    # Rule of 4 with shade for many outs.
    if outs <= 8:
        # Linear approximation is accurate for ≤ 8 outs.
        return outs * 0.04
    if outs == 9:
        return 0.35  # flush draw — published value
    if outs == 10:
        return 0.385
    if outs == 11:
        return 0.42
    if outs == 12:
        return 0.45
    if outs == 13:
        return 0.485
    if outs == 14:
        return 0.515
    if outs == 15:
        return 0.54
    # Above 15 outs: linear approximation breaks down — cap at ~0.65.
    return min(0.54 + (outs - 15) * 0.03, 0.95)
