"""
routers/leaderboard.py — Leaderboard endpoint for BetWise Casino.

Design constraints (specs/betwise-casino.md §T14):
- _top_n helper is the single SQL statement for leaderboard.
- Returns top 20 by chip_balance DESC.
- Accuracy = correct_decisions / total_hands * 100 (0 for users with 0 hands).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas import LeaderboardRowOut

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("", response_model=list[LeaderboardRowOut])
async def get_leaderboard(
    db: AsyncSession = Depends(get_db),
) -> list[LeaderboardRowOut]:
    """Return the top 20 users sorted by chip_balance descending."""
    return await _top_n(20, db)


# ─── SQL helpers ─────────────────────────────────────────────────────────────

async def _top_n(n: int, db: AsyncSession) -> list[LeaderboardRowOut]:
    """Single query: top N users by chip_balance DESC."""
    from sqlalchemy import select, desc  # noqa: PLC0415
    from backend.models import User  # noqa: PLC0415

    result = await db.execute(
        select(User).order_by(desc(User.chip_balance)).limit(n)
    )
    users = result.scalars().all()

    return [
        LeaderboardRowOut(
            rank=i + 1,
            user_id=u.id,
            username=u.username,
            chip_balance=u.chip_balance,
            total_hands=u.total_hands,
            accuracy_pct=(
                u.correct_decisions / u.total_hands * 100.0
                if u.total_hands > 0
                else 0.0
            ),
            best_streak=u.best_streak,
        )
        for i, u in enumerate(users)
    ]
