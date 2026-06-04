"""
test_pai_gow_fortune.py — unit tests for Fortune qualifying detection and
the bet-proportional / pool payout schedule (spec §11).

Coverage map to the review points called out:
- Tier exclusivity: one hand → one (tier, category). Higher preempts lower.
- Best-5-of-7 criterion (§11.1) for non-GRAND tiers.
- Straight-flush tier (added round-6 — plain SF gets 200×, between 4K=50× and
  royal flush = MAJOR pool tier).
- $5 pool-qualifying bet boundary (§7.8): below $5, pool hands fall back to
  the 200× fixed multiplier.
- Pool-tier helpers (concurrency tests with the actual DB lock live in
  test_pai_gow_concurrency.py in Phase 6 — here we test only the pure math).
"""
from __future__ import annotations

import pytest

from backend.game.pai_gow.fortune import (
    CONTRIBUTION_PER_DEAL_CENTS,
    FIXED_MULTIPLIERS,
    POOL_QUALIFYING_BET_CENTS,
    FortuneCategory,
    FortuneQualification,
    FortuneTier,
    classify_fortune,
    fixed_payout_cents,
    pool_payout_cents,
)


_SUIT_SHORT = {"h": "hearts", "d": "diamonds", "c": "clubs", "s": "spades"}


def C(suit: str, value: str) -> dict:
    return {"suit": _SUIT_SHORT.get(suit, suit), "value": value}


# ─── Non-qualifying / edge ───────────────────────────────────────────────────


def test_zero_bet_returns_none_even_on_winning_hand():
    """No fortune bet placed → never evaluate, even on a 4-of-a-kind hand."""
    seven = [
        C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    assert classify_fortune(seven, fortune_bet_cents=0) is None


def test_high_card_returns_none():
    seven = [
        C("h", "A"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "7"), C("s", "5"), C("c", "3"),
    ]
    assert classify_fortune(seven, fortune_bet_cents=500) is None


def test_one_pair_returns_none():
    seven = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "9"),
        C("h", "7"), C("s", "5"), C("c", "3"),
    ]
    assert classify_fortune(seven, fortune_bet_cents=500) is None


def test_two_pair_returns_none():
    seven = [
        C("h", "K"), C("s", "K"), C("d", "Q"), C("c", "Q"),
        C("h", "7"), C("s", "5"), C("c", "3"),
    ]
    assert classify_fortune(seven, fortune_bet_cents=500) is None


# ─── Fixed tier per category (best-5-of-7 criterion) ─────────────────────────


def test_three_of_a_kind_fixed_2x():
    seven = [
        C("h", "9"), C("s", "9"), C("d", "9"),
        C("c", "K"), C("h", "J"), C("s", "5"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.THREE_OF_A_KIND)


def test_straight_fixed_3x():
    seven = [
        C("h", "9"), C("s", "8"), C("d", "7"), C("c", "6"), C("h", "5"),
        C("s", "K"), C("c", "2"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT)


def test_flush_fixed_4x():
    seven = [
        C("h", "K"), C("h", "Q"), C("h", "9"), C("h", "5"), C("h", "2"),
        C("s", "3"), C("c", "7"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.FLUSH)


def test_full_house_fixed_5x():
    seven = [
        C("h", "9"), C("s", "9"), C("d", "9"),
        C("c", "K"), C("h", "K"), C("s", "5"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.FULL_HOUSE)


def test_four_of_a_kind_fixed_50x():
    seven = [
        C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"),
        C("h", "5"), C("s", "3"), C("c", "2"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.FOUR_OF_A_KIND)


def test_plain_straight_flush_fixed_200x():
    """9-high SF (non-royal) → FIXED + STRAIGHT_FLUSH at 200× (round-6 add)."""
    seven = [
        C("h", "9"), C("h", "8"), C("h", "7"), C("h", "6"), C("h", "5"),
        C("s", "3"), C("c", "2"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT_FLUSH)


def test_wheel_straight_flush_is_NOT_royal():
    """A-2-3-4-5 SF (wheel SF, rank 9) is NOT royal (rank 10). Fixed tier."""
    seven = [
        C("h", "A"), C("h", "2"), C("h", "3"), C("h", "4"), C("h", "5"),
        C("s", "K"), C("c", "Q"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT_FLUSH)


# ─── Pool tier — qualifying bet boundary at $5 (§7.8) ────────────────────────


def test_royal_flush_with_qualifying_bet_is_MAJOR():
    """A-K-Q-J-10 of hearts with fortune_bet >= 500 → MAJOR."""
    seven = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "10"),
        C("s", "5"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=500)
    assert q == FortuneQualification(FortuneTier.MAJOR, FortuneCategory.ROYAL_FLUSH)


def test_royal_flush_below_qualifying_bet_falls_back_to_FIXED_SF():
    """Royal flush at fortune_bet < 500 → FIXED + SF 200× (the §11.2 fallback)."""
    seven = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "10"),
        C("s", "5"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT_FLUSH)


def test_seven_card_sf_with_qualifying_bet_is_GRAND():
    """All 7 cards form a SF and bet >= $5 → GRAND."""
    seven = [
        C("h", "2"), C("h", "3"), C("h", "4"), C("h", "5"),
        C("h", "6"), C("h", "7"), C("h", "8"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=500)
    assert q == FortuneQualification(FortuneTier.GRAND, FortuneCategory.SEVEN_CARD_SF)


def test_seven_card_sf_below_qualifying_bet_falls_back_to_FIXED_SF():
    """7-card SF at fortune_bet < 500 → FIXED + SF 200× (same §11.2 fallback)."""
    seven = [
        C("h", "2"), C("h", "3"), C("h", "4"), C("h", "5"),
        C("h", "6"), C("h", "7"), C("h", "8"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q == FortuneQualification(FortuneTier.FIXED, FortuneCategory.STRAIGHT_FLUSH)


def test_qualifying_bet_exactly_500_qualifies():
    """The boundary is INCLUSIVE — fortune_bet == 500 is pool-eligible."""
    seven = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "10"),
        C("s", "5"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=POOL_QUALIFYING_BET_CENTS)
    assert q is not None and q.tier is FortuneTier.MAJOR


def test_qualifying_bet_499_falls_back():
    """One cent below boundary → fall back."""
    seven = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"), C("h", "10"),
        C("s", "5"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=499)
    assert q is not None and q.tier is FortuneTier.FIXED


# ─── Tier exclusivity (one hand → exactly one tier+category) ─────────────────


def test_GRAND_preempts_MAJOR_when_hand_qualifies_for_both():
    """A-K-Q-J-10-9-8 hearts: best-5 is royal flush, AND all 7 form a SF.
    Both GRAND (7-card SF) and MAJOR (royal in best-5) apply. GRAND wins.
    """
    seven = [
        C("h", "A"), C("h", "K"), C("h", "Q"), C("h", "J"),
        C("h", "10"), C("h", "9"), C("h", "8"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=500)
    assert q == FortuneQualification(FortuneTier.GRAND, FortuneCategory.SEVEN_CARD_SF)


def test_full_house_returns_FULL_HOUSE_not_THREE_OF_A_KIND():
    """A full house contains a three-of-a-kind, but classification is for the
    full house only (one tier, one category per hand)."""
    seven = [
        C("h", "9"), C("s", "9"), C("d", "9"),
        C("c", "K"), C("h", "K"), C("s", "5"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q is not None
    assert q.category is FortuneCategory.FULL_HOUSE


def test_four_of_a_kind_preempts_full_house_when_only_one_category_applies():
    """KKKK + 9 9 X → quads of K (not full house because there are no trips
    of 9 either way). Just verify the evaluator+classify pick the right one."""
    seven = [
        C("h", "K"), C("s", "K"), C("d", "K"), C("c", "K"),
        C("h", "9"), C("s", "9"), C("c", "3"),
    ]
    q = classify_fortune(seven, fortune_bet_cents=100)
    assert q is not None
    assert q.category is FortuneCategory.FOUR_OF_A_KIND


# ─── Bet-proportional fixed payouts (round-6 redesign) ───────────────────────


def test_fixed_payout_four_of_a_kind_50x_scales_with_bet():
    assert fixed_payout_cents(FortuneCategory.FOUR_OF_A_KIND, 100) == 5_000
    assert fixed_payout_cents(FortuneCategory.FOUR_OF_A_KIND, 1_000) == 50_000


def test_fixed_payout_straight_flush_200x():
    assert fixed_payout_cents(FortuneCategory.STRAIGHT_FLUSH, 100) == 20_000
    assert fixed_payout_cents(FortuneCategory.STRAIGHT_FLUSH, 500) == 100_000


def test_fixed_payout_full_house_5x():
    assert fixed_payout_cents(FortuneCategory.FULL_HOUSE, 1_000) == 5_000


def test_fixed_payout_flush_4x():
    assert fixed_payout_cents(FortuneCategory.FLUSH, 1_000) == 4_000


def test_fixed_payout_straight_3x():
    assert fixed_payout_cents(FortuneCategory.STRAIGHT, 1_000) == 3_000


def test_fixed_payout_three_of_a_kind_2x():
    assert fixed_payout_cents(FortuneCategory.THREE_OF_A_KIND, 1_000) == 2_000


def test_bet_proportional_at_5_vs_100_dollar_bets():
    """Same hand at $5 (500c) vs $100 (10000c) → 20× scaling."""
    low = fixed_payout_cents(FortuneCategory.FOUR_OF_A_KIND, 500)
    high = fixed_payout_cents(FortuneCategory.FOUR_OF_A_KIND, 10_000)
    assert high == low * 20


def test_fixed_payout_rejects_pool_categories():
    """SEVEN_CARD_SF / ROYAL_FLUSH must go through pool_payout_cents.
    Calling fixed_payout_cents on them surfaces the bug as KeyError."""
    with pytest.raises(KeyError):
        fixed_payout_cents(FortuneCategory.SEVEN_CARD_SF, 1_000)
    with pytest.raises(KeyError):
        fixed_payout_cents(FortuneCategory.ROYAL_FLUSH, 1_000)


# ─── Pool payouts (pure math; lock + DB writes belong to state.py § 11.4) ────


def test_pool_GRAND_payout_drains_to_seed():
    """GRAND: payout = pool - seed; new_pool = seed."""
    payout, new_pool = pool_payout_cents(
        FortuneTier.GRAND, pool_amount_cents=500_000, seed_cents=100_000
    )
    assert payout == 400_000
    assert new_pool == 100_000


def test_pool_MAJOR_payout_half_of_surplus():
    """MAJOR: payout = (pool - seed) // 2; new_pool = pool - payout."""
    payout, new_pool = pool_payout_cents(
        FortuneTier.MAJOR, pool_amount_cents=500_000, seed_cents=100_000
    )
    assert payout == 200_000
    assert new_pool == 300_000


def test_pool_GRAND_at_seed_returns_zero():
    """Second concurrent GRAND winner: pool already at seed → payout=0,
    pool unchanged. Matches §11.4 — first winner takes all, second collects 0.
    """
    payout, new_pool = pool_payout_cents(
        FortuneTier.GRAND, pool_amount_cents=100_000, seed_cents=100_000
    )
    assert payout == 0
    assert new_pool == 100_000


def test_pool_MAJOR_at_seed_returns_zero():
    payout, new_pool = pool_payout_cents(
        FortuneTier.MAJOR, pool_amount_cents=100_000, seed_cents=100_000
    )
    assert payout == 0
    assert new_pool == 100_000


def test_pool_MAJOR_integer_floor_no_float_drift():
    """Odd surplus → MAJOR floors at //2. Integer-cents discipline (CLAUDE.md #4)."""
    payout, new_pool = pool_payout_cents(
        FortuneTier.MAJOR, pool_amount_cents=100_001, seed_cents=100_000
    )
    assert payout == 0   # 1 // 2 == 0
    assert new_pool == 100_001


def test_pool_payout_rejects_FIXED_tier():
    """FIXED is house-funded; pool_payout_cents on it is a state.py bug."""
    with pytest.raises(ValueError):
        pool_payout_cents(
            FortuneTier.FIXED, pool_amount_cents=500_000, seed_cents=100_000
        )


# ─── Constants verbatim ──────────────────────────────────────────────────────


def test_contribution_constant_is_25_cents():
    """§11.3: fixed 25¢ per qualifying deal."""
    assert CONTRIBUTION_PER_DEAL_CENTS == 25


def test_pool_qualifying_bet_constant_is_500():
    """§7.8: $5 = 500 cents minimum to qualify for GRAND/MAJOR."""
    assert POOL_QUALIFYING_BET_CENTS == 500


def test_fixed_multipliers_verbatim_from_spec():
    """§11.2 fixed-tier multipliers — pinned values, must not drift silently."""
    assert FIXED_MULTIPLIERS[FortuneCategory.STRAIGHT_FLUSH] == 200
    assert FIXED_MULTIPLIERS[FortuneCategory.FOUR_OF_A_KIND] == 50
    assert FIXED_MULTIPLIERS[FortuneCategory.FULL_HOUSE] == 5
    assert FIXED_MULTIPLIERS[FortuneCategory.FLUSH] == 4
    assert FIXED_MULTIPLIERS[FortuneCategory.STRAIGHT] == 3
    assert FIXED_MULTIPLIERS[FortuneCategory.THREE_OF_A_KIND] == 2


# ─── Convenience predicates on FortuneQualification ──────────────────────────


def test_qualification_is_pool_tier_true_for_GRAND():
    q = FortuneQualification(FortuneTier.GRAND, FortuneCategory.SEVEN_CARD_SF)
    assert q.is_pool_tier is True
    assert q.is_fixed_tier is False


def test_qualification_is_pool_tier_true_for_MAJOR():
    q = FortuneQualification(FortuneTier.MAJOR, FortuneCategory.ROYAL_FLUSH)
    assert q.is_pool_tier is True


def test_qualification_is_fixed_tier_for_FIXED():
    q = FortuneQualification(FortuneTier.FIXED, FortuneCategory.FLUSH)
    assert q.is_fixed_tier is True
    assert q.is_pool_tier is False


# ─── Input validation ────────────────────────────────────────────────────────


def test_classify_rejects_non_7_card_input():
    with pytest.raises(ValueError):
        classify_fortune([C("h", "A")], fortune_bet_cents=500)
