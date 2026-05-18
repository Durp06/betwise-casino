"""
test_weakness.py — unit tests for the silver-piece weakness aggregation engine.

Criteria source: specs/betwise-casino.md §T8, §7.
Import path: backend.analytics.weakness
(ModuleNotFoundError until T8 lands)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.analytics.weakness import _categorize, get_weak_spots


# ─── helpers ─────────────────────────────────────────────────────────────────

def card(value: str, suit: str = "spades") -> dict:
    return {"suit": suit, "value": value}


def make_action_row(
    hand_snapshot: list,
    dealer_upcard: dict,
    was_correct: bool,
) -> dict:
    """Minimal dict that mirrors a PlayerAction row for test purposes."""
    return {
        "hand_snapshot": hand_snapshot,
        "dealer_upcard": dealer_upcard,
        "was_correct": was_correct,
    }


# ─── _categorize unit tests ───────────────────────────────────────────────────
# Criterion: _categorize(hand_snapshot, dealer_upcard) -> tuple[str, str]
# is a pure function (no DB) that buckets a hand.

def test_categorize_hard_16_against_10():
    # Hard 16 (9+7) vs dealer 10 → ("hard_12-16", "10")
    hand = [card("9"), card("7")]
    dealer = card("10")
    cat, dealer_cat = _categorize(hand, dealer)
    assert cat == "hard_12-16", f"Expected 'hard_12-16', got {cat!r}"
    assert dealer_cat == "10", f"Expected dealer category '10', got {dealer_cat!r}"


def test_categorize_pair_aces():
    # A-A is pair_aces regardless of dealer upcard
    hand = [card("A"), card("A")]
    dealer = card("6")
    cat, _ = _categorize(hand, dealer)
    assert cat == "pair_aces", f"Expected 'pair_aces', got {cat!r}"


def test_categorize_soft_18_against_dealer_3():
    # A+7 = soft 18, dealer 3 → ("soft_18+", "2-3")
    hand = [card("A"), card("7")]
    dealer = card("3")
    cat, dealer_cat = _categorize(hand, dealer)
    assert cat == "soft_18+", f"Expected 'soft_18+', got {cat!r}"
    assert dealer_cat == "2-3", f"Expected dealer category '2-3', got {dealer_cat!r}"


def test_categorize_dealer_ten_upcard():
    # Dealer value 10 → dealer_upcard_category = "10"
    hand = [card("K"), card("6")]  # hard 16
    dealer = card("10")
    _, dealer_cat = _categorize(hand, dealer)
    assert dealer_cat == "10", f"Expected '10', got {dealer_cat!r}"


# ─── get_weak_spots integration (async, uses mocked DB) ───────────────────────
# Criterion: new user (0 actions) → returns empty list, not error.

@pytest.mark.asyncio
async def test_empty_user_returns_empty_list():
    """User with no player_actions rows returns [] without raising."""
    mock_db = MagicMock()
    # Simulate SELECT returning zero rows
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    user_id = uuid.uuid4()
    result = await get_weak_spots(user_id, mock_db)
    assert result == [], f"Expected [], got {result!r}"


# Criterion: bucket with fewer than 5 samples is filtered out.

@pytest.mark.asyncio
async def test_bucket_with_less_than_5_samples_filtered_out():
    """4 actions in one bucket → that bucket does not appear in output."""
    mock_db = MagicMock()

    # 4 rows all in the same bucket (hard 16 vs dealer 10)
    rows = [
        MagicMock(
            hand_snapshot=[card("9"), card("7")],
            dealer_upcard=card("10"),
            was_correct=(i == 0),  # 1 correct, 3 wrong
        )
        for i in range(4)
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    mock_db.execute = AsyncMock(return_value=mock_result)

    user_id = uuid.uuid4()
    result = await get_weak_spots(user_id, mock_db)
    assert result == [], (
        "Bucket with 4 samples (< 5) must be filtered out; got non-empty result"
    )


# Criterion: 5 actions in a bucket, 1 correct → accuracy == 0.2

@pytest.mark.asyncio
async def test_bucket_with_5_samples_1_correct_returns_accuracy_0_2():
    """5 rows in one bucket with 1 correct → one WeakSpotOut with accuracy=0.2."""
    mock_db = MagicMock()

    rows = [
        MagicMock(
            hand_snapshot=[card("9"), card("7")],  # hard 16
            dealer_upcard=card("10"),
            was_correct=(i == 0),  # only first row correct
        )
        for i in range(5)
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    mock_db.execute = AsyncMock(return_value=mock_result)

    user_id = uuid.uuid4()
    result = await get_weak_spots(user_id, mock_db)
    assert len(result) == 1, f"Expected 1 weak spot, got {len(result)}"
    spot = result[0]
    assert spot.samples == 5
    assert spot.correct == 1
    assert abs(spot.accuracy - 0.2) < 1e-9, f"Expected accuracy 0.2, got {spot.accuracy}"


# Criterion: output is sorted ascending by accuracy (worst first).

@pytest.mark.asyncio
async def test_results_sorted_worst_first():
    """Multiple buckets → sorted by accuracy ascending (lowest accuracy first)."""
    mock_db = MagicMock()

    # Bucket A: hard 16 vs dealer 10 — 5 samples, 4 correct (accuracy 0.8)
    bucket_a = [
        MagicMock(
            hand_snapshot=[card("9"), card("7")],
            dealer_upcard=card("10"),
            was_correct=(i < 4),
        )
        for i in range(5)
    ]
    # Bucket B: soft 18 vs dealer 9 — 5 samples, 1 correct (accuracy 0.2)
    bucket_b = [
        MagicMock(
            hand_snapshot=[card("A"), card("7")],
            dealer_upcard=card("9"),
            was_correct=(i == 0),
        )
        for i in range(5)
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = bucket_b + bucket_a  # deliberately disordered
    mock_db.execute = AsyncMock(return_value=mock_result)

    user_id = uuid.uuid4()
    result = await get_weak_spots(user_id, mock_db)
    assert len(result) == 2, f"Expected 2 weak spots, got {len(result)}"
    # Worst accuracy first
    assert result[0].accuracy <= result[1].accuracy, (
        "Results must be sorted ascending by accuracy (worst first)"
    )
    assert abs(result[0].accuracy - 0.2) < 1e-9, "Worst spot should have accuracy 0.2"
    assert abs(result[1].accuracy - 0.8) < 1e-9, "Better spot should have accuracy 0.8"
