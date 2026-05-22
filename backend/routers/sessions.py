"""
routers/sessions.py — Session-level endpoints for BetWise Casino.

GET /api/sessions/{session_id}/review is the Hand Review modal feed.
Access rule mirrors the single-hand replay: caller must own a hand in
the session, OR the session must be finished. SQL is centralized in
the `_get_session_review` helper at the bottom; the handler is thin.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import SessionReviewOut

router = APIRouter(tags=["sessions"])


@router.get("/sessions/{session_id}/review", response_model=SessionReviewOut)
async def get_session_review(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> SessionReviewOut:
    return await _get_session_review(session_id, current_user, db)


# ─── SQL helpers ─────────────────────────────────────────────────────────────

async def _get_session_review(
    session_id: uuid.UUID,
    current_user_id: uuid.UUID,
    db: AsyncSession,
) -> SessionReviewOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import GameSession, Hand, PlayerAction  # noqa: PLC0415
    from backend.schemas import ReviewActionOut  # noqa: PLC0415
    from backend.game.review import classify_action  # noqa: PLC0415

    # Fetch session
    result = await db.execute(select(GameSession).where(GameSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fetch caller's hand in this session
    result = await db.execute(
        select(Hand).where(
            (Hand.session_id == session_id) & (Hand.user_id == current_user_id)
        )
    )
    caller_hand = result.scalar_one_or_none()

    if caller_hand is None:
        # Owner-or-finished rule
        if session.status == "finished":
            raise HTTPException(status_code=404, detail="No hand to review in this session")
        raise HTTPException(
            status_code=403,
            detail="Cannot view review while session is in progress without a hand",
        )

    # Fetch actions ordered ascending by created_at
    result = await db.execute(
        select(PlayerAction)
        .where(PlayerAction.hand_id == caller_hand.id)
        .order_by(PlayerAction.created_at)
    )
    actions = result.scalars().all()

    review_actions: list[ReviewActionOut] = []
    total = 0
    optimal = 0
    ev_total = 0
    worst_id: uuid.UUID | None = None
    worst_loss = 0

    # hand.bet stores the FINAL bet, which has doubled if the player ever
    # took the "double" action. To compute per-action EV losses honestly we
    # need to know the bet at the moment of each decision: pre-double
    # decisions risked the initial bet; the double itself risked 2x.
    has_double = any(a.action == "double" for a in actions)
    initial_bet = caller_hand.bet // 2 if has_double else caller_hand.bet

    for a in actions:
        total += 1
        if a.was_correct:
            optimal += 1
        bet_at_action = initial_bet * 2 if a.action == "double" else initial_bet
        cls, loss = classify_action(
            a.hand_snapshot, a.dealer_upcard, a.action, a.optimal_action, bet_at_action,
        )
        ev_total += loss
        if loss > worst_loss:
            worst_loss = loss
            worst_id = a.id
        review_actions.append(ReviewActionOut(
            id=a.id,
            hand_id=a.hand_id,
            user_id=a.user_id,
            action=a.action,
            player_guess=a.player_guess,
            optimal_action=a.optimal_action,
            was_correct=a.was_correct,
            hand_snapshot=a.hand_snapshot,
            dealer_upcard=a.dealer_upcard,
            chipy_explanation=a.chipy_explanation,
            created_at=a.created_at,
            classification=cls,
            ev_loss_chips=loss,
        ))

    accuracy = (optimal / total) if total > 0 else 0.0

    return SessionReviewOut(
        session_id=session.id,
        hand_id=caller_hand.id,
        total_actions=total,
        optimal_count=optimal,
        accuracy=accuracy,
        ev_lost_chips=ev_total,
        worst_action_id=worst_id,
        actions=review_actions,
    )
