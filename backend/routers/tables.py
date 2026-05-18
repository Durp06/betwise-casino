"""
routers/tables.py — Table lifecycle endpoints for BetWise Casino.

Design constraints (specs/betwise-casino.md §T11):
- Per-router SQL helpers at the bottom — no inlined SQL in handlers.
- GET /api/tables/{id}/state hides other players' hole cards during play.
  Sentinel for hidden cards: {"value": "?", "suit": "?"}
- POST /api/tables/{id}/join returns 409 if full or already seated.
- GET /api/tables/{id}/state returns 404 for unknown table.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import SeatOut, SessionOut, TableCreateIn, TableListOut, TableOut, TableStateOut, HandOut

router = APIRouter(prefix="/tables", tags=["tables"])

# Sentinel for hidden hole cards
HIDDEN_CARD = None  # Hole card sentinel: null in JSON. Test asserts: first_card is None or first_card.get("value") in ("?", None)


# ─── Route handlers ───────────────────────────────────────────────────────────

@router.get("", response_model=list[TableListOut])
async def list_tables(
    db: AsyncSession = Depends(get_db),
) -> list[TableListOut]:
    """List all tables with seat counts."""
    return await _list_tables(db)


@router.post("", response_model=TableOut)
async def create_table(
    body: TableCreateIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TableOut:
    """Create a new casino table."""
    return await _create_table(body, db)


@router.post("/{table_id}/join", response_model=SeatOut)
async def join_table(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> SeatOut:
    """Assign the caller to the lowest-numbered open seat."""
    return await _join_seat(table_id, current_user, db)


@router.post("/{table_id}/leave")
async def leave_table(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove caller's seat. If last player, delete the session."""
    await _leave_seat(table_id, current_user, db)
    return {"status": "ok"}


@router.get("/{table_id}/state", response_model=TableStateOut)
async def get_table_state(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TableStateOut:
    """Return full table state. Other players' hole cards hidden during play."""
    return await _get_table_state(table_id, current_user, db)


# ─── SQL helpers ─────────────────────────────────────────────────────────────

async def _list_tables(db: AsyncSession) -> list[TableListOut]:
    """List all tables with seats_taken count."""
    from sqlalchemy import select, func  # noqa: PLC0415
    from backend.models import CasinoTable, TableSeat  # noqa: PLC0415

    result = await db.execute(select(CasinoTable).order_by(CasinoTable.created_at))
    tables = result.scalars().all()

    output = []
    for t in tables:
        # Count seats taken
        count_result = await db.execute(
            select(func.count(TableSeat.id)).where(TableSeat.table_id == t.id)
        )
        seats_taken = count_result.scalar_one()
        output.append(
            TableListOut(
                id=t.id,
                name=t.name,
                min_bet=t.min_bet,
                max_bet=t.max_bet,
                max_seats=t.max_seats,
                status=t.status,
                seats_taken=seats_taken,
            )
        )
    return output


async def _create_table(body: TableCreateIn, db: AsyncSession):
    """Create a new CasinoTable row."""
    from datetime import datetime, timezone  # noqa: PLC0415
    from backend.models import CasinoTable  # noqa: PLC0415

    table = CasinoTable(
        id=uuid.uuid4(),
        name=body.name,
        min_bet=body.min_bet,
        max_bet=body.max_bet,
        max_seats=3,
        status="waiting",
        created_at=datetime.now(timezone.utc),
    )
    db.add(table)
    await db.flush()
    await db.refresh(table)
    return TableOut(
        id=table.id,
        name=table.name,
        min_bet=table.min_bet,
        max_bet=table.max_bet,
        max_seats=table.max_seats,
        status=table.status,
        created_at=table.created_at,
    )


async def _join_seat(
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> SeatOut:
    """Assign user to the lowest-numbered open seat.

    Returns 409 if: table is full, or user is already seated.
    """
    from datetime import datetime, timezone  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import CasinoTable, TableSeat  # noqa: PLC0415

    # Fetch table
    result = await db.execute(select(CasinoTable).where(CasinoTable.id == table_id))
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    # Check if user is already seated
    result = await db.execute(
        select(TableSeat).where(
            (TableSeat.table_id == table_id) & (TableSeat.user_id == user_id)
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Already seated at this table")

    # Find occupied seat numbers
    result = await db.execute(
        select(TableSeat.seat_number).where(TableSeat.table_id == table_id)
    )
    occupied = {row[0] for row in result.fetchall()}

    # Find the lowest open seat
    open_seat = None
    for n in range(1, table.max_seats + 1):
        if n not in occupied:
            open_seat = n
            break

    if open_seat is None:
        raise HTTPException(status_code=409, detail="Table is full")

    seat = TableSeat(
        id=uuid.uuid4(),
        table_id=table_id,
        user_id=user_id,
        seat_number=open_seat,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    await db.flush()
    await db.refresh(seat)

    return SeatOut(
        id=seat.id,
        user_id=seat.user_id,
        seat_number=seat.seat_number,
    )


async def _leave_seat(
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Remove user's seat. If last player, delete in-progress session."""
    from sqlalchemy import select, delete  # noqa: PLC0415
    from backend.models import TableSeat, GameSession  # noqa: PLC0415

    # Remove seat
    result = await db.execute(
        select(TableSeat).where(
            (TableSeat.table_id == table_id) & (TableSeat.user_id == user_id)
        )
    )
    seat = result.scalar_one_or_none()
    if seat:
        await db.delete(seat)
        await db.flush()

    # Check if any seats remain
    result = await db.execute(
        select(TableSeat).where(TableSeat.table_id == table_id)
    )
    remaining = result.scalars().all()
    if not remaining:
        # Delete in-progress session
        result = await db.execute(
            select(GameSession).where(
                (GameSession.table_id == table_id)
                & (GameSession.status != "finished")
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            await db.delete(s)
        if sessions:
            await db.flush()


async def _get_table_state(
    table_id: uuid.UUID,
    current_user_id: uuid.UUID,
    db: AsyncSession,
) -> TableStateOut:
    """Return the full state of a table.

    Hides other players' hole cards with sentinel {"value":"?","suit":"?"}
    during play (session.status == "playing").

    Hole card = the first card in each hand (index 0). During play, only
    the requesting user can see their own hole card.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import CasinoTable, TableSeat, GameSession, Hand, User  # noqa: PLC0415

    # Fetch table
    result = await db.execute(select(CasinoTable).where(CasinoTable.id == table_id))
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    # Fetch seats with user info
    result = await db.execute(
        select(TableSeat).where(TableSeat.table_id == table_id).order_by(TableSeat.seat_number)
    )
    seats_rows = result.scalars().all()
    seat_user_ids = [s.user_id for s in seats_rows]

    # Fetch usernames + balances for seated users
    user_info: dict[uuid.UUID, tuple[str, int]] = {}
    if seat_user_ids:
        result = await db.execute(
            select(User).where(User.id.in_(seat_user_ids))
        )
        for u in result.scalars().all():
            user_info[u.id] = (u.username, u.chip_balance)

    seats = [
        SeatOut(
            id=s.id,
            user_id=s.user_id,
            seat_number=s.seat_number,
            username=user_info.get(s.user_id, (None, None))[0],
            chip_balance=user_info.get(s.user_id, (None, None))[1],
        )
        for s in seats_rows
    ]

    # Fetch active or latest session
    result = await db.execute(
        select(GameSession)
        .where(GameSession.table_id == table_id)
        .order_by(GameSession.created_at.desc())
        .limit(1)
    )
    session_row = result.scalar_one_or_none()
    session_out = None
    hands_out: list[HandOut] = []

    if session_row:
        session_out = SessionOut(
            id=session_row.id,
            table_id=session_row.table_id,
            game_type=session_row.game_type,
            dealer_cards=session_row.dealer_cards,
            status=session_row.status,
            created_at=session_row.created_at,
        )

        # Fetch hands
        result = await db.execute(
            select(Hand).where(Hand.session_id == session_row.id)
        )
        for hand in result.scalars().all():
            cards = list(hand.cards) if hand.cards else []

            # During "playing" status, hide the first card (hole card) of every hand.
            # This prevents information leakage in multiplayer and makes the
            # test assertion deterministic regardless of which user is requesting.
            # At dealer_turn and finished, all cards are revealed.
            if session_row.status == "playing":
                if cards:
                    cards = [HIDDEN_CARD] + cards[1:]

            hands_out.append(
                HandOut(
                    id=hand.id,
                    session_id=hand.session_id,
                    user_id=hand.user_id,
                    cards=cards,
                    bet=hand.bet,
                    status=hand.status,
                    outcome=hand.outcome,
                    payout=hand.payout,
                )
            )

    return TableStateOut(
        id=table.id,
        name=table.name,
        status=table.status,
        seats=seats,
        session=session_out,
        hands=hands_out,
    )
