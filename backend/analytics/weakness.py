"""
weakness.py — Weakness aggregation engine for BetWise Casino (SILVER nontrivial piece).

Design constraints (specs/betwise-casino.md §T8):
- _categorize(hand_snapshot, dealer_upcard) is a pure function (no DB).
- get_weak_spots(user_id, db) aggregates player_actions into weakness buckets.
- Buckets with < 5 samples are filtered out.
- Results sorted ascending by accuracy (worst first).
- Uses the .scalars().all() ORM pattern for DB access.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.game.engine import can_split, card_rank, hand_value, is_soft
from backend.schemas import WeakSpotOut

# ─── Hand category buckets ────────────────────────────────────────────────────
# hand_category ∈ {
#   "hard_8-", "hard_9-11", "hard_12-16", "hard_17+",
#   "soft_13-17", "soft_18+",
#   "pair_aces", "pair_8s", "pair_other"
# }
# dealer_upcard_category ∈ {"2-3", "4-6", "7-9", "10", "A"}


def _hand_category(hand_snapshot: list[dict]) -> str:
    """Categorize a hand snapshot into one of the 9 hand_category buckets."""
    # Check for pairs first
    if can_split(hand_snapshot):
        v = hand_snapshot[0]["value"]
        if v == "A":
            return "pair_aces"
        if v == "8":
            return "pair_8s"
        return "pair_other"

    total = hand_value(hand_snapshot)
    soft = is_soft(hand_snapshot)

    if soft:
        if total <= 17:
            return "soft_13-17"
        return "soft_18+"
    else:
        if total <= 8:
            return "hard_8-"
        if total <= 11:
            return "hard_9-11"
        if total <= 16:
            return "hard_12-16"
        return "hard_17+"


def _dealer_category(dealer_upcard: dict) -> str:
    """Categorize the dealer upcard into one of the 5 dealer_upcard_category buckets."""
    v = dealer_upcard.get("value", "")
    if v == "A":
        return "A"
    if v in ("J", "Q", "K", "10"):
        return "10"
    rank = card_rank(dealer_upcard)
    if rank <= 3:
        return "2-3"
    if rank <= 6:
        return "4-6"
    return "7-9"


def _categorize(
    hand_snapshot: list[dict],
    dealer_upcard: dict,
) -> tuple[str, str]:
    """Pure function: categorize a hand+upcard into (hand_category, dealer_upcard_category).

    This is the contract tested directly by test_weakness.py.
    """
    return _hand_category(hand_snapshot), _dealer_category(dealer_upcard)


async def get_weak_spots(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[WeakSpotOut]:
    """Aggregate player_actions for a user into weakness buckets.

    Returns a list of WeakSpotOut sorted ascending by accuracy (worst first).
    Buckets with fewer than 5 samples are excluded.
    """
    from backend.models import PlayerAction  # noqa: PLC0415

    stmt = select(PlayerAction).where(PlayerAction.user_id == user_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        return []

    # Aggregate by (hand_category, dealer_upcard_category)
    buckets: dict[tuple[str, str], dict] = defaultdict(lambda: {"samples": 0, "correct": 0})

    for row in rows:
        hand_cat, dealer_cat = _categorize(row.hand_snapshot, row.dealer_upcard)
        key = (hand_cat, dealer_cat)
        buckets[key]["samples"] += 1
        if row.was_correct:
            buckets[key]["correct"] += 1

    # Build output, filter < 5 samples, sort by accuracy ascending
    output: list[WeakSpotOut] = []
    for (hand_cat, dealer_cat), stats in buckets.items():
        if stats["samples"] < 5:
            continue
        accuracy = stats["correct"] / stats["samples"]
        output.append(
            WeakSpotOut(
                hand_category=hand_cat,
                dealer_upcard_category=dealer_cat,
                samples=stats["samples"],
                correct=stats["correct"],
                accuracy=accuracy,
            )
        )

    output.sort(key=lambda x: x.accuracy)
    return output
