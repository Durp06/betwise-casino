"""
routers/users.py — User CRUD + stats endpoints for BetWise Casino.

Design constraints (specs/betwise-casino.md §T10):
- Each query is in a private _helper function at the bottom — no inlined SQL in handlers.
- POST /api/users/me is idempotent (upsert).
- GET /api/users/me returns UserStatsOut with streak fields.
- POST /api/users/me/reset-chips returns 409 when balance >= 1000.
- GET /api/users/{id}/hands returns [] (not 404) for user with no hands.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import HandOut, UserCreateIn, UserStatsOut

router = APIRouter(prefix="/users", tags=["users"])


# ─── Route handlers ───────────────────────────────────────────────────────────

@router.get("/me", response_model=UserStatsOut)
async def get_me(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserStatsOut:
    """Return the authenticated user's profile + stats."""
    user = await _get_user_by_id(current_user, db)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    accuracy = (
        user.correct_decisions / user.total_hands
        if user.total_hands > 0
        else 0.0
    )
    return UserStatsOut(
        id=user.id,
        username=user.username,
        chip_balance=user.chip_balance,
        total_hands=user.total_hands,
        correct_decisions=user.correct_decisions,
        accuracy=accuracy,
        current_streak=user.current_streak,
        best_streak=user.best_streak,
        created_at=user.created_at,
    )


@router.post("/me", response_model=UserStatsOut)
async def upsert_me(
    body: UserCreateIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserStatsOut:
    """Create or return existing user row (idempotent first-login upsert)."""
    user = await _upsert_user(current_user, body.username, db)
    accuracy = (
        user.correct_decisions / user.total_hands
        if user.total_hands > 0
        else 0.0
    )
    return UserStatsOut(
        id=user.id,
        username=user.username,
        chip_balance=user.chip_balance,
        total_hands=user.total_hands,
        correct_decisions=user.correct_decisions,
        accuracy=accuracy,
        current_streak=user.current_streak,
        best_streak=user.best_streak,
        created_at=user.created_at,
    )


@router.post("/me/reset-chips", response_model=UserStatsOut)
async def reset_chips(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserStatsOut:
    """Reset chip balance to 100000 only when balance < 1000; else 409."""
    user = await _get_user_by_id(current_user, db)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.chip_balance >= 1000:
        raise HTTPException(
            status_code=409,
            detail=f"Not eligible — balance is ${user.chip_balance / 100:.2f}",
        )

    user.chip_balance = 100_000
    await db.flush()
    await db.refresh(user)
    accuracy = (
        user.correct_decisions / user.total_hands
        if user.total_hands > 0
        else 0.0
    )
    return UserStatsOut(
        id=user.id,
        username=user.username,
        chip_balance=user.chip_balance,
        total_hands=user.total_hands,
        correct_decisions=user.correct_decisions,
        accuracy=accuracy,
        current_streak=user.current_streak,
        best_streak=user.best_streak,
        created_at=user.created_at,
    )


@router.get("/{user_id}/hands", response_model=list[HandOut])
async def get_user_hands(
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[HandOut]:
    """Return the caller's last 20 hands (approximate insertion order). Cannot view another player's history."""
    if user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="Cannot view another player's hand history",
        )
    hands = await _get_user_hands(user_id, db)
    return [
        HandOut(
            id=h.id,
            session_id=h.session_id,
            user_id=h.user_id,
            cards=h.cards,
            bet=h.bet,
            status=h.status,
            outcome=h.outcome,
            payout=h.payout,
        )
        for h in hands
    ]


# ─── SQL helpers (no inlined SQL in handlers above) ─────────────────────────

async def _get_user_by_id(user_id: uuid.UUID, db: AsyncSession):
    """Fetch a user by ID, or return None."""
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import User  # noqa: PLC0415

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _upsert_user(user_id: uuid.UUID, username: str, db: AsyncSession):
    """Fetch existing user or create new one with the given username.

    Idempotent: if user already exists, return as-is (ignore username arg).
    """
    from datetime import datetime, timezone  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import User  # noqa: PLC0415

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        id=user_id,
        username=username,
        chip_balance=100_000,
        total_hands=0,
        correct_decisions=0,
        current_streak=0,
        best_streak=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def _get_user_hands(user_id: uuid.UUID, db: AsyncSession) -> list:
    """Return last 20 hands for user, ordered newest-first."""
    from sqlalchemy import select, desc  # noqa: PLC0415
    from backend.models import Hand  # noqa: PLC0415

    result = await db.execute(
        select(Hand)
        .where(Hand.user_id == user_id)
        .order_by(desc(Hand.session_id))  # approximate newest-first by session
        .limit(20)
    )
    return list(result.scalars().all())
