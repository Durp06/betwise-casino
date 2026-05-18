"""
routers/analytics.py — Analytics endpoints for BetWise Casino.

Design constraints (specs/betwise-casino.md §T14):
- GET /api/analytics/weakness requires authentication.
- Delegates to analytics.weakness.get_weak_spots — no re-implementation of bucketing.
- Returns 200 with [] for a new user with no actions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import WeakSpotOut

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/weakness", response_model=list[WeakSpotOut])
async def get_weakness(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[WeakSpotOut]:
    """Return this user's weakness spots. Returns [] if no data."""
    from backend.analytics.weakness import get_weak_spots  # noqa: PLC0415

    return await get_weak_spots(current_user, db)
