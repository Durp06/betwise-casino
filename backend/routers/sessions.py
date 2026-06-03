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
    from backend.game.blackjack import ev as ev_mod  # noqa: PLC0415
    from backend.game.blackjack.odds import dealer_bust_pct  # noqa: PLC0415
    from backend.game.blackjack.engine import can_double as _can_double, can_split as _can_split  # noqa: PLC0415

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
    sharp_count = 0
    blunder_count = 0

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

        # Classify action using EV-delta grading (Task 4 / review.py).
        cls, loss = classify_action(
            a.hand_snapshot, a.dealer_upcard, a.action, a.optimal_action, bet_at_action,
        )
        ev_total += loss
        if loss > worst_loss:
            worst_loss = loss
            worst_id = a.id

        # Aggregate sharp/blunder counts (AC-S-REV2 / AC-R-REV2).
        if cls == "sharp":
            sharp_count += 1
        elif cls == "blunder":
            blunder_count += 1

        # EV enrichment: compute per-action EV breakdown via ev.py (AC-S-REV1 / AC-R-REV1).
        # EV math is pure-sync — no await needed.
        snapshot = list(a.hand_snapshot)
        upcard = a.dealer_upcard
        if snapshot:
            c_double = _can_double(snapshot)  # type: ignore[arg-type]
            c_split = _can_split(snapshot)  # type: ignore[arg-type]
            action_evs_map = ev_mod.action_evs(snapshot, upcard, can_double=c_double, can_split=c_split)
            best_act, b_ev = ev_mod.best_action_ev(snapshot, upcard, can_double=c_double, can_split=c_split)
            ev_of_played = action_evs_map.get(a.action)
            if ev_of_played is None:
                ev_of_played = b_ev  # fallback for unmodeled actions (e.g., split)
            ev_delta_val = max(0.0, b_ev - ev_of_played)
            d_bust_pct = dealer_bust_pct(upcard)
        else:
            action_evs_map = {}
            best_act = ""
            b_ev = 0.0
            ev_delta_val = 0.0
            d_bust_pct = 0.0

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
            action_evs=action_evs_map,
            best_action=best_act,
            best_ev=b_ev,
            ev_delta=ev_delta_val,
            dealer_bust_pct=d_bust_pct,
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
        sharp_count=sharp_count,
        blunder_count=blunder_count,
    )
