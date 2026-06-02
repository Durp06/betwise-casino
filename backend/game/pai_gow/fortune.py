"""backend.game.pai_gow.fortune — Fortune progressive side bet logic.

Pure functions. Classifies a 7-card hand into a Fortune qualification
(tier + category) and computes payout amounts. Concurrency / DB lock
handling lives in state.py — it calls our pure helpers inside the
`SELECT … FOR UPDATE` transaction described in spec §11.4.

Tier hierarchy (most → least lucrative):
  GRAND  — 7-card straight flush. fortune_bet >= $5. Drains pool to seed.
  MAJOR  — Royal flush in best 5. fortune_bet >= $5. Pays half pool surplus.
  FIXED  — Any other qualifying hand. House-funded; bet × multiplier.

Tier classification is EXCLUSIVE: one hand → one (tier, category). Higher
tiers preempt lower. GRAND is checked first, then MAJOR (via best-5
detection of royal flush), then the fixed-tier categories in evaluator's
natural ordering.

§7.8 qualifying-bet rule: below $5 (500 cents), pool-tier hands fall back
to FIXED + STRAIGHT_FLUSH so the player still gets the 200× multiplier.

Spec refs: §11 (Fortune pool design), §7.8 (qualifying bet), §11.4
(concurrency model — uses these helpers inside the row lock).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from backend.game.pai_gow.cards import Card
from backend.game.pai_gow.evaluator import (
    FLUSH as _EV_FLUSH,
    FOUR_OF_A_KIND as _EV_4K,
    FULL_HOUSE as _EV_FH,
    STRAIGHT as _EV_STRAIGHT,
    STRAIGHT_FLUSH as _EV_SF,
    THREE_OF_A_KIND as _EV_3K,
    best_five_card_hand,
    is_seven_card_straight_flush,
)


# ─── Constants (spec §11.2, §11.3, §7.8) ─────────────────────────────────────

# Fixed cents added to the pool per deal that carries any fortune_bet > 0,
# independent of bet size. House margin covers the rest of the bet. §11.3.
CONTRIBUTION_PER_DEAL_CENTS: int = 25

# Minimum fortune_bet (cents) to qualify for pool tier (GRAND / MAJOR). Below
# this, royal flush / 7-card SF fall back to the 200× SF fixed multiplier —
# matches real-casino "qualifying bet" semantics. §7.8.
POOL_QUALIFYING_BET_CENTS: int = 500

# Royal-flush detection: evaluator encodes A-K-Q-J-10 straights as rank 10
# (spec §7.2). Any STRAIGHT_FLUSH score with second tuple element == 10 is
# a royal; ranks 1..9 are plain SFs (incl. wheel SF at rank 9 — NOT royal).
_ROYAL_STRAIGHT_RANK: int = 10


# ─── Enums + dataclass ──────────────────────────────────────────────────────


class FortuneTier(str, Enum):
    GRAND = "grand"   # 7-card SF, drains pool to seed
    MAJOR = "major"   # Royal flush in best 5, pays half pool surplus
    FIXED = "fixed"   # Any other qualifying hand; bet × multiplier


class FortuneCategory(str, Enum):
    SEVEN_CARD_SF = "seven_card_sf"
    ROYAL_FLUSH = "royal_flush"
    STRAIGHT_FLUSH = "straight_flush"   # plain SF (incl. wheel) + qualifying-bet fallback
    FOUR_OF_A_KIND = "four_of_a_kind"
    FULL_HOUSE = "full_house"
    FLUSH = "flush"
    STRAIGHT = "straight"
    THREE_OF_A_KIND = "three_of_a_kind"


@dataclass(frozen=True)
class FortuneQualification:
    """A 7-card hand's Fortune classification. Always exactly one tier and
    one category — never multiple. Use `is_pool_tier` / `is_fixed_tier` for
    dispatch in state.py (pool tier needs the row lock; fixed tier doesn't).
    """
    tier: FortuneTier
    category: FortuneCategory

    @property
    def is_pool_tier(self) -> bool:
        return self.tier in (FortuneTier.GRAND, FortuneTier.MAJOR)

    @property
    def is_fixed_tier(self) -> bool:
        return self.tier is FortuneTier.FIXED


# Bet × multiplier table for fixed-tier payouts. Spec §11.2 verbatim.
# STRAIGHT_FLUSH lives here too (non-royal SF + qualifying-bet fallback).
FIXED_MULTIPLIERS: dict[FortuneCategory, int] = {
    FortuneCategory.STRAIGHT_FLUSH:   200,
    FortuneCategory.FOUR_OF_A_KIND:    50,
    FortuneCategory.FULL_HOUSE:         5,
    FortuneCategory.FLUSH:              4,
    FortuneCategory.STRAIGHT:           3,
    FortuneCategory.THREE_OF_A_KIND:    2,
}


# ─── Public API ──────────────────────────────────────────────────────────────


def classify_fortune(
    seven_cards: list[Card],
    fortune_bet_cents: int,
) -> Optional[FortuneQualification]:
    """Determine the Fortune qualification for a 7-card hand.

    Returns None when:
      - `fortune_bet_cents <= 0` (no Fortune side bet placed), or
      - hand doesn't reach the THREE_OF_A_KIND fixed-tier floor.

    Otherwise returns exactly one `FortuneQualification`. Tier classification
    is EXCLUSIVE: GRAND preempts MAJOR preempts FIXED. The $5 qualifying-bet
    boundary (§7.8) is applied here — pool-tier hands at fortune_bet < 500
    fall back to FIXED + STRAIGHT_FLUSH.
    """
    if len(seven_cards) != 7:
        raise ValueError(f"classify_fortune expects 7 cards, got {len(seven_cards)}")
    if fortune_bet_cents <= 0:
        return None

    qualifies_for_pool = fortune_bet_cents >= POOL_QUALIFYING_BET_CENTS

    # GRAND first — 7-card SF is rarer than any 5-card category and preempts
    # the royal-flush MAJOR check when both apply (e.g., A-K-Q-J-10-9-8 SF).
    if is_seven_card_straight_flush(seven_cards):
        if qualifies_for_pool:
            return FortuneQualification(FortuneTier.GRAND, FortuneCategory.SEVEN_CARD_SF)
        return FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT_FLUSH)

    # MAJOR + remaining fixed-tier categories use best-5-of-7 per §11.1.
    _, score = best_five_card_hand(seven_cards)
    category_code = score[0]

    if category_code == _EV_SF:
        is_royal = score[1] == _ROYAL_STRAIGHT_RANK
        if is_royal:
            if qualifies_for_pool:
                return FortuneQualification(FortuneTier.MAJOR, FortuneCategory.ROYAL_FLUSH)
            # Royal flush below qualifying bet → 200× fixed-SF fallback.
            return FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT_FLUSH)
        # Plain SF (incl. wheel SF rank 9): FIXED + STRAIGHT_FLUSH (200×).
        return FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT_FLUSH)

    if category_code == _EV_4K:
        return FortuneQualification(FortuneTier.FIXED, FortuneCategory.FOUR_OF_A_KIND)
    if category_code == _EV_FH:
        return FortuneQualification(FortuneTier.FIXED, FortuneCategory.FULL_HOUSE)
    if category_code == _EV_FLUSH:
        return FortuneQualification(FortuneTier.FIXED, FortuneCategory.FLUSH)
    if category_code == _EV_STRAIGHT:
        return FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT)
    if category_code == _EV_3K:
        return FortuneQualification(FortuneTier.FIXED, FortuneCategory.THREE_OF_A_KIND)

    # Two pair / one pair / high card → no Fortune payout.
    return None


def fixed_payout_cents(category: FortuneCategory, fortune_bet_cents: int) -> int:
    """FIXED-tier payout: `multiplier × bet`. Raises KeyError if called with
    a pool-tier category (SEVEN_CARD_SF / ROYAL_FLUSH) — that's a state.py
    bug; pool-tier payouts must go through pool_payout_cents.
    """
    return FIXED_MULTIPLIERS[category] * fortune_bet_cents


def pool_payout_cents(
    tier: FortuneTier,
    pool_amount_cents: int,
    seed_cents: int,
) -> tuple[int, int]:
    """Pure pool-tier math. Returns `(payout_cents, new_pool_amount_cents)`.

    Caller is responsible for the `SELECT … FOR UPDATE` row lock on
    fortune_pool, the subsequent `UPDATE fortune_pool SET amount_cents = …`
    write, and the matching fortune_pool_events ledger entry — all within a
    single DB transaction per spec §11.4.

    GRAND: payout = pool − seed; new_pool = seed (drains).
    MAJOR: payout = (pool − seed) // 2 (integer floor); new_pool = pool − payout.

    If `pool_amount_cents <= seed_cents` (e.g., the prior winner just drained
    the pool), payout is 0 and the pool is unchanged — correct casino
    behavior for the second-concurrent-winner case. The row lock means only
    one transaction sees the surplus; the next observes the post-drain state.

    Raises ValueError on FIXED tier — that's a state.py routing bug.
    """
    if tier is FortuneTier.FIXED:
        raise ValueError("pool_payout_cents called with FIXED tier; use fixed_payout_cents")

    if pool_amount_cents <= seed_cents:
        return 0, pool_amount_cents

    surplus = pool_amount_cents - seed_cents
    if tier is FortuneTier.GRAND:
        return surplus, seed_cents
    # MAJOR — integer-floor division keeps us in integer cents (CLAUDE.md #4).
    payout = surplus // 2
    return payout, pool_amount_cents - payout
