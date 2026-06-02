"""routers/pai_gow_tables.py — Pai Gow table lifecycle endpoints.

Endpoints (spec §13):
  POST   /api/pai-gow/tables                — create a PG table
  GET    /api/pai-gow/tables                — list PG tables + seat counts
  POST   /api/pai-gow/tables/{id}/join      — claim the lowest open seat
  POST   /api/pai-gow/tables/{id}/leave     — release seat + escrow refund (§9.6)
  GET    /api/pai-gow/tables/{id}/state     — full polled state (3s loop)

Card-visibility masking is applied in the `state` handler per spec §13:
- During `betting` / `playing`, other players' dealt_cards / front / back are
  hidden (sentinel `null`); the dealer's dealt_cards / front / back are
  hidden.
- During `dealer_turn` / `finished`, everything is revealed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.game.pai_gow import state as pg_state
from backend.schemas import (
    PaiGowPlayerHandOut,
    PaiGowRoundOut,
    PaiGowSeatOut,
    PaiGowTableCreateIn,
    PaiGowTableListItemOut,
    PaiGowTableOut,
    PaiGowTableStateOut,
)

router = APIRouter(prefix="/pai-gow/tables", tags=["pai-gow-tables"])


# ─── Route handlers ──────────────────────────────────────────────────────────


@router.post("", response_model=PaiGowTableOut, status_code=201)
async def create_table(
    body: PaiGowTableCreateIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PaiGowTableOut:
    """Create a new Pai Gow table."""
    if body.max_bet_cents < body.min_bet_cents:
        raise HTTPException(status_code=400, detail="max_bet must be >= min_bet")
    if body.max_fortune_bet_cents < body.min_fortune_bet_cents:
        raise HTTPException(status_code=400, detail="max_fortune_bet must be >= min_fortune_bet")
    return await _create_table(body, db)


@router.get("", response_model=list[PaiGowTableListItemOut])
async def list_tables(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[PaiGowTableListItemOut]:
    """List PG tables with seat counts + active round status."""
    return await _list_tables(db)


@router.post("/{table_id}/join", response_model=PaiGowSeatOut)
async def join_table(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PaiGowSeatOut:
    """Claim the lowest-numbered open seat at this PG table."""
    return await _join_seat(table_id, current_user, db)


@router.post("/{table_id}/leave")
async def leave_table(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Release seat + refund escrow if leaving during an active round (§9.6)."""
    await pg_state.leave_table_with_refund(db, table_id, current_user)
    return {"status": "ok"}


@router.get("/{table_id}/state", response_model=PaiGowTableStateOut)
async def get_table_state(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PaiGowTableStateOut:
    """Full polled state for the PG table page. Masks other players' cards
    until `dealer_turn` / `finished` per spec §13.
    """
    return await _get_table_state(table_id, current_user, db)


# ─── SQL helpers ────────────────────────────────────────────────────────────


async def _create_table(
    body: PaiGowTableCreateIn, db: AsyncSession
) -> PaiGowTableOut:
    from backend.models import PaiGowTable  # noqa: PLC0415

    table = PaiGowTable(
        id=uuid.uuid4(),
        name=body.name,
        min_bet_cents=body.min_bet_cents,
        max_bet_cents=body.max_bet_cents,
        min_fortune_bet_cents=body.min_fortune_bet_cents,
        max_fortune_bet_cents=body.max_fortune_bet_cents,
        max_seats=body.max_seats,
        created_at=datetime.now(timezone.utc),
    )
    db.add(table)
    await db.flush()
    await db.refresh(table)
    return PaiGowTableOut.model_validate(table)


async def _list_tables(db: AsyncSession) -> list[PaiGowTableListItemOut]:
    from backend.models import PaiGowRound, PaiGowSeat, PaiGowTable  # noqa: PLC0415

    result = await db.execute(
        select(PaiGowTable).order_by(PaiGowTable.created_at)
    )
    tables = result.scalars().all()
    out: list[PaiGowTableListItemOut] = []
    for t in tables:
        # Seat count
        seat_count = (
            await db.execute(
                select(func.count())
                .select_from(PaiGowSeat)
                .where(PaiGowSeat.table_id == t.id)
            )
        ).scalar_one()
        # Active round status
        active = (
            await db.execute(
                select(PaiGowRound)
                .where(PaiGowRound.table_id == t.id)
                .where(PaiGowRound.status.in_(("betting", "playing", "dealer_turn")))
                .order_by(PaiGowRound.round_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append(PaiGowTableListItemOut(
            id=t.id,
            name=t.name,
            min_bet_cents=t.min_bet_cents,
            max_bet_cents=t.max_bet_cents,
            max_seats=t.max_seats,
            seats_taken=int(seat_count),
            active_round_status=active.status if active is not None else None,
        ))
    return out


async def _join_seat(
    table_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> PaiGowSeatOut:
    from backend.models import PaiGowSeat, PaiGowTable  # noqa: PLC0415

    table = await db.execute(
        select(PaiGowTable).where(PaiGowTable.id == table_id)
    )
    table_row = table.scalar_one_or_none()
    if table_row is None:
        raise HTTPException(status_code=404, detail="Pai Gow table not found")

    # Idempotent: if already seated, return existing seat.
    existing = (
        await db.execute(
            select(PaiGowSeat)
            .where(PaiGowSeat.table_id == table_id)
            .where(PaiGowSeat.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return PaiGowSeatOut.model_validate(existing)

    # Race-safe seat claim. UNIQUE(table_id, seat_number) means two concurrent
    # joins that both pick seat N collide; the loser would 500 without a
    # savepoint. Same pattern as state._find_or_create_active_round (fix B):
    # wrap the speculative INSERT in db.begin_nested() so the savepoint rolls
    # back on IntegrityError but the outer txn lives. On the next iteration we
    # recompute the occupied set (which now includes the winning concurrent
    # claim) and pick the next open seat.
    #
    # Bounded by max_seats — worst case every seat is contested. Adequate for
    # the max_seats=3 v1 cap; v2 with larger tables can revisit if needed.
    for _attempt in range(table_row.max_seats):
        occupied = {
            n for (n,) in (
                await db.execute(
                    select(PaiGowSeat.seat_number).where(PaiGowSeat.table_id == table_id)
                )
            ).fetchall()
        }
        open_seat: Optional[int] = next(
            (n for n in range(1, table_row.max_seats + 1) if n not in occupied),
            None,
        )
        if open_seat is None:
            raise HTTPException(status_code=409, detail="Table is full")

        new_seat = PaiGowSeat(
            id=uuid.uuid4(),
            table_id=table_id,
            user_id=user_id,
            seat_number=open_seat,
            joined_at=datetime.now(timezone.utc),
        )
        try:
            async with db.begin_nested():
                db.add(new_seat)
                await db.flush()
        except IntegrityError:
            # Savepoint rolled back the failed INSERT AND detached the
            # instance from session tracking — no explicit expunge needed.
            # Recompute occupied + retry with the next seat.
            continue
        # Refresh intentionally skipped — all PaiGowSeatOut fields are set
        # Python-side (no server defaults to read back) and the savepoint +
        # async-session refresh combination misbehaves under concurrency.
        return PaiGowSeatOut.model_validate(new_seat)

    # Exhausted retries — only reachable under pathological concurrency
    # where every seat got claimed between our SELECT and INSERT on each
    # iteration. Surface as 500 so it's visible if it ever fires.
    raise HTTPException(
        status_code=500,
        detail="Failed to claim a seat after retries",
    )


async def _get_table_state(
    table_id: uuid.UUID, current_user_id: uuid.UUID, db: AsyncSession
) -> PaiGowTableStateOut:
    """Build the full state-snapshot response with card-visibility masking."""
    from backend.models import (  # noqa: PLC0415
        FORTUNE_POOL_SINGLETON_ID,
        FortunePool,
        PaiGowPlayerHand,
        PaiGowSeat,
        PaiGowTable,
        User,
    )

    table_row = (
        await db.execute(select(PaiGowTable).where(PaiGowTable.id == table_id))
    ).scalar_one_or_none()
    if table_row is None:
        raise HTTPException(status_code=404, detail="Pai Gow table not found")

    # Seats + usernames + balances
    seat_rows = (
        await db.execute(
            select(PaiGowSeat)
            .where(PaiGowSeat.table_id == table_id)
            .order_by(PaiGowSeat.seat_number)
        )
    ).scalars().all()
    user_ids = [s.user_id for s in seat_rows]
    users_map: dict[uuid.UUID, User] = {}
    if user_ids:
        user_rows = (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars().all()
        users_map = {u.id: u for u in user_rows}
    seats_out = [
        PaiGowSeatOut(
            id=s.id,
            user_id=s.user_id,
            seat_number=s.seat_number,
            username=users_map.get(s.user_id).username if users_map.get(s.user_id) else None,
            chip_balance=users_map.get(s.user_id).chip_balance if users_map.get(s.user_id) else None,
        )
        for s in seat_rows
    ]

    # Active round (with lazy timeout check)
    rnd = await pg_state.get_active_round_state(db, table_id, current_user_id)

    round_out: Optional[PaiGowRoundOut] = None
    hands_out: list[PaiGowPlayerHandOut] = []
    if rnd is not None:
        reveal_all = rnd.status in ("dealer_turn", "finished")
        round_out = PaiGowRoundOut(
            id=rnd.id,
            table_id=rnd.table_id,
            round_number=rnd.round_number,
            dealer_dealt_cards=list(rnd.dealer_dealt_cards) if reveal_all else None,
            dealer_front=list(rnd.dealer_front) if (reveal_all and rnd.dealer_front) else None,
            dealer_back=list(rnd.dealer_back) if (reveal_all and rnd.dealer_back) else None,
            status=rnd.status,
            playing_started_at=rnd.playing_started_at,
            created_at=rnd.created_at,
            resolved_at=rnd.resolved_at,
        )
        hand_rows = (
            await db.execute(
                select(PaiGowPlayerHand).where(PaiGowPlayerHand.round_id == rnd.id)
            )
        ).scalars().all()
        for h in hand_rows:
            is_owner = h.user_id == current_user_id
            show_cards = is_owner or reveal_all
            hands_out.append(PaiGowPlayerHandOut(
                id=h.id,
                round_id=h.round_id,
                user_id=h.user_id,
                dealt_cards=list(h.dealt_cards) if show_cards else None,
                front_cards=list(h.front_cards) if (show_cards and h.front_cards) else None,
                back_cards=list(h.back_cards) if (show_cards and h.back_cards) else None,
                bet_cents=h.bet_cents,
                fortune_bet_cents=h.fortune_bet_cents,
                front_compare=h.front_compare,
                back_compare=h.back_compare,
                hand_result=h.hand_result,
                ante_payout_cents=h.ante_payout_cents,
                fortune_payout_cents=h.fortune_payout_cents,
                action_status=h.action_status,
                created_at=h.created_at,
                resolved_at=h.resolved_at,
            ))

    # Current Fortune pool amount (inline so polling only takes one round-trip).
    pool_amount = (
        await db.execute(
            select(FortunePool.amount_cents)
            .where(FortunePool.id == FORTUNE_POOL_SINGLETON_ID)
        )
    ).scalar_one_or_none() or 0

    return PaiGowTableStateOut(
        id=table_row.id,
        name=table_row.name,
        min_bet_cents=table_row.min_bet_cents,
        max_bet_cents=table_row.max_bet_cents,
        min_fortune_bet_cents=table_row.min_fortune_bet_cents,
        max_fortune_bet_cents=table_row.max_fortune_bet_cents,
        max_seats=table_row.max_seats,
        seats=seats_out,
        round=round_out,
        hands=hands_out,
        fortune_pool_amount_cents=int(pool_amount),
    )
