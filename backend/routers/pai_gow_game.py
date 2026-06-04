"""routers/pai_gow_game.py — Pai Gow round-level game endpoints.

Endpoints (spec §13):
  POST   /api/pai-gow/tables/{id}/deal           — place ante + fortune bet, deal 7 cards
  POST   /api/pai-gow/hands/{id}/set             — submit player split
  GET    /api/pai-gow/hands/{id}/replay          — hand replay (player_actions)
  GET    /api/pai-gow/fortune-pool               — current pool amount
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from backend.auth import CurrentUser
from backend.database import get_db
from backend.game.pai_gow import state as pg_state
from backend.ratelimit import MUTATION_RATE_LIMIT, limiter
from backend.schemas import (
    FortunePoolOut,
    PaiGowDealIn,
    PaiGowPlayerHandOut,
    PaiGowReplayActionOut,
    PaiGowSetIn,
)

router = APIRouter(prefix="/pai-gow", tags=["pai-gow-game"])


# ─── Route handlers ─────────────────────────────────────────────────────────


@router.post("/tables/{table_id}/deal", response_model=PaiGowPlayerHandOut)
@limiter.limit(MUTATION_RATE_LIMIT)
async def deal(
    request: Request,
    table_id: uuid.UUID,
    body: PaiGowDealIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PaiGowPlayerHandOut:
    """Place ante + optional fortune bet, deal 7 cards. Idempotent per
    `(round_id, user_id)` — client double-fire returns the existing hand.
    """
    request.state.user_id = str(current_user)  # per-user rate-limit key
    hand = await pg_state.deal_to_player(
        db,
        table_id=table_id,
        user_id=current_user,
        bet_cents=body.bet_cents,
        fortune_bet_cents=body.fortune_bet_cents,
    )
    return _hand_to_out(hand)


@router.post("/hands/{hand_id}/set", response_model=PaiGowPlayerHandOut)
@limiter.limit(MUTATION_RATE_LIMIT)
async def set_hand(
    request: Request,
    hand_id: uuid.UUID,
    body: PaiGowSetIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PaiGowPlayerHandOut:
    """Submit the player's split (front=2 cards, back=5 cards).

    Returns the resolved hand if this set triggered the round's resolution
    (eager check per §9.3 step 6) — otherwise the hand in `set` status.
    """
    request.state.user_id = str(current_user)  # per-user rate-limit key
    hand = await pg_state.submit_player_set(
        db,
        hand_id=hand_id,
        user_id=current_user,
        front=body.front,
        back=body.back,
    )
    return _hand_to_out(hand)


@router.get(
    "/hands/{hand_id}/replay",
    response_model=list[PaiGowReplayActionOut],
)
async def hand_replay(
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[PaiGowReplayActionOut]:
    """Replay timeline for the hand. Owner can read anytime; others can read
    only after the round status is `finished`.
    """
    return await _get_replay(hand_id, current_user, db)


@router.get("/fortune-pool", response_model=FortunePoolOut)
async def get_fortune_pool(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> FortunePoolOut:
    """Current Fortune progressive pool amount + seed + last update time."""
    return await _get_fortune_pool(db)


# ─── SQL / serialization helpers ────────────────────────────────────────────


def _hand_to_out(hand) -> PaiGowPlayerHandOut:
    """Owner-visible serialization — used by deal + set endpoints where the
    caller IS the hand owner.
    """
    return PaiGowPlayerHandOut(
        id=hand.id,
        round_id=hand.round_id,
        user_id=hand.user_id,
        dealt_cards=list(hand.dealt_cards) if hand.dealt_cards else None,
        front_cards=list(hand.front_cards) if hand.front_cards else None,
        back_cards=list(hand.back_cards) if hand.back_cards else None,
        bet_cents=hand.bet_cents,
        fortune_bet_cents=hand.fortune_bet_cents,
        front_compare=hand.front_compare,
        back_compare=hand.back_compare,
        hand_result=hand.hand_result,
        ante_payout_cents=hand.ante_payout_cents,
        fortune_payout_cents=hand.fortune_payout_cents,
        action_status=hand.action_status,
        created_at=hand.created_at,
        resolved_at=hand.resolved_at,
    )


async def _get_replay(
    hand_id: uuid.UUID,
    current_user_id: uuid.UUID,
    db: AsyncSession,
) -> list[PaiGowReplayActionOut]:
    from backend.models import PaiGowPlayerAction, PaiGowPlayerHand, PaiGowRound  # noqa: PLC0415

    hand = (
        await db.execute(
            select(PaiGowPlayerHand).where(PaiGowPlayerHand.id == hand_id)
        )
    ).scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Pai Gow hand not found")

    rnd = (
        await db.execute(
            select(PaiGowRound).where(PaiGowRound.id == hand.round_id)
        )
    ).scalar_one_or_none()

    is_owner = hand.user_id == current_user_id
    finished = rnd is not None and rnd.status == "finished"
    if not is_owner and not finished:
        raise HTTPException(
            status_code=403,
            detail="Cannot view replay while the round is in progress",
        )

    actions = (
        await db.execute(
            select(PaiGowPlayerAction)
            .where(PaiGowPlayerAction.hand_id == hand_id)
            .order_by(PaiGowPlayerAction.created_at)
        )
    ).scalars().all()
    return [
        PaiGowReplayActionOut(
            id=a.id,
            hand_id=a.hand_id,
            user_id=a.user_id,
            action_type=a.action_type,
            player_front=list(a.player_front) if a.player_front else None,
            player_back=list(a.player_back) if a.player_back else None,
            optimal_front=list(a.optimal_front),
            optimal_back=list(a.optimal_back),
            was_optimal=a.was_optimal,
            chipy_explanation=a.chipy_explanation,
            created_at=a.created_at,
        )
        for a in actions
    ]


async def _get_fortune_pool(db: AsyncSession) -> FortunePoolOut:
    from backend.models import FORTUNE_POOL_SINGLETON_ID, FortunePool  # noqa: PLC0415

    pool = (
        await db.execute(
            select(FortunePool).where(FortunePool.id == FORTUNE_POOL_SINGLETON_ID)
        )
    ).scalar_one_or_none()
    if pool is None:
        # Defensive: pool singleton should always exist (seeded by migration).
        raise HTTPException(status_code=500, detail="Fortune pool not initialized")
    return FortunePoolOut.model_validate(pool)
