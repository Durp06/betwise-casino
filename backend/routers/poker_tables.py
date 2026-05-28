"""
routers/poker_tables.py — Texas Hold'em tournament lobby + state endpoints.

Design constraints (specs/texas-holdem.md §AC-R1..R5):
- POST /api/poker/tournaments creates a tournament, deducts buy-in from the
  user's bankroll, assigns random archetypes, creates seats. Atomic.
- GET /api/poker/tournaments lists active tournaments the current user is in.
- GET /api/poker/tournaments/{id}/state returns the tournament + seats + the
  current hand snapshot. Hole cards visible only to current_user's own seat.
- Single SQL helper per router, prefixed `_`, at the bottom (CLAUDE.md rule).
- Lazy imports inside handlers with # noqa: PLC0415.

Brief §4.5: tournament chips and bankroll cents are separate integer units.
Conversion only at buy-in (cents → deducted) and payout (cents → credited).
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import (
    PokerSeatOut,
    PokerTournamentCreateIn,
    PokerTournamentOut,
    PokerTournamentStateOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/poker/tournaments", tags=["poker_tables"])


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("", response_model=PokerTournamentOut, status_code=201)
async def create_tournament(
    body: PokerTournamentCreateIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PokerTournamentOut:
    """Create a new SNG tournament, deduct buy-in, assign random archetypes."""
    if not (2 <= body.bot_count <= 7):
        raise HTTPException(status_code=400, detail="bot_count must be between 2 and 7")
    if body.advice_mode not in ("reads", "odds"):
        raise HTTPException(status_code=400, detail="advice_mode must be 'reads' or 'odds'")
    if body.buy_in_cents <= 0:
        raise HTTPException(status_code=400, detail="buy_in_cents must be positive")
    if body.starting_stack_chips <= 0:
        raise HTTPException(status_code=400, detail="starting_stack_chips must be positive")

    return await _create_tournament_with_seats(current_user, body, db)


@router.get("", response_model=list[PokerTournamentOut])
async def list_my_tournaments(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[PokerTournamentOut]:
    """Return the active tournaments the current user is a seat in."""
    return await _list_user_tournaments(current_user, db)


@router.get("/{tournament_id}/state", response_model=PokerTournamentStateOut)
async def get_state(
    tournament_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PokerTournamentStateOut:
    """Polled endpoint. Returns the tournament + seats + (optionally) the
    current hand state. Hole cards visible only to current_user's seat."""
    return await _get_tournament_state(tournament_id, current_user, db)


# ─── SQL helpers (single-source per router) ───────────────────────────────────


async def _create_tournament_with_seats(
    current_user: uuid.UUID,
    body: PokerTournamentCreateIn,
    db: AsyncSession,
) -> PokerTournamentOut:
    """Atomic: deducts buy-in, creates tournament row, creates seats."""
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.archetypes import assign_random_archetypes  # noqa: PLC0415
    from backend.models import PokerSeat, PokerTournament, User  # noqa: PLC0415

    # Look up user; check bankroll
    user = (await db.execute(select(User).where(User.id == current_user))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.chip_balance < body.buy_in_cents:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient bankroll: have {user.chip_balance}¢, need {body.buy_in_cents}¢",
        )

    seed = random.randint(0, 2**31 - 1)
    tournament = PokerTournament(
        id=uuid.uuid4(),
        bot_count=body.bot_count,
        advice_mode=body.advice_mode,
        buy_in_cents=body.buy_in_cents,
        starting_stack_chips=body.starting_stack_chips,
        hands_per_level=body.hands_per_level,
        seed=seed,
        status="active",
        button_seat=0,
        current_hand_number=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tournament)
    await db.flush()  # ensure tournament.id is bindable for seats

    # Deduct bankroll
    user.chip_balance -= body.buy_in_cents

    # Assign archetypes randomly (per brief §7 mandate)
    rng = random.Random(seed)
    archetypes = assign_random_archetypes(body.bot_count, rng=rng, guarantee_variety=False)

    # Create seats — human first (seat 0), then bots
    seats = [
        PokerSeat(
            id=uuid.uuid4(),
            tournament_id=tournament.id,
            user_id=current_user,
            seat_number=0,
            archetype_name=None,
            starting_stack=body.starting_stack_chips,
            current_stack=body.starting_stack_chips,
            is_bust=False,
            is_bot=False,
            joined_at=datetime.now(timezone.utc),
        )
    ]
    for i, spec in enumerate(archetypes, start=1):
        seats.append(
            PokerSeat(
                id=uuid.uuid4(),
                tournament_id=tournament.id,
                user_id=None,
                seat_number=i,
                archetype_name=spec.name,
                starting_stack=body.starting_stack_chips,
                current_stack=body.starting_stack_chips,
                is_bust=False,
                is_bot=True,
                joined_at=datetime.now(timezone.utc),
            )
        )
    db.add_all(seats)
    await db.commit()
    await db.refresh(tournament)

    return PokerTournamentOut.model_validate(tournament)


async def _list_user_tournaments(
    current_user: uuid.UUID,
    db: AsyncSession,
) -> list[PokerTournamentOut]:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import PokerSeat, PokerTournament  # noqa: PLC0415

    stmt = (
        select(PokerTournament)
        .join(PokerSeat, PokerSeat.tournament_id == PokerTournament.id)
        .where(PokerSeat.user_id == current_user)
        .order_by(PokerTournament.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return [PokerTournamentOut.model_validate(t) for t in rows]


async def _get_tournament_state(
    tournament_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> PokerTournamentStateOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import PokerSeat, PokerTournament  # noqa: PLC0415

    tournament = (await db.execute(
        select(PokerTournament).where(PokerTournament.id == tournament_id)
    )).scalar_one_or_none()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    seats = (await db.execute(
        select(PokerSeat)
        .where(PokerSeat.tournament_id == tournament_id)
        .order_by(PokerSeat.seat_number)
    )).scalars().all()

    your_seat = next((s for s in seats if s.user_id == current_user), None)
    if your_seat is None:
        # User not a participant — refuse (brief: every endpoint takes
        # current_user and checks ownership).
        raise HTTPException(status_code=403, detail="Not a participant in this tournament")

    return PokerTournamentStateOut(
        tournament=PokerTournamentOut.model_validate(tournament),
        seats=[PokerSeatOut.model_validate(s) for s in seats],
        current_hand=None,  # hand state assembled by poker_game router (Phase 4)
        your_seat_number=your_seat.seat_number,
    )
