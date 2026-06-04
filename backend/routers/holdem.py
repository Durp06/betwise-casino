"""
routers/holdem.py — multiplayer Texas Hold'em (cash ring game) endpoints.

Mirrors the multiplayer-blackjack table conventions (lobby / join / leave /
polled state / deal / action) but for Hold'em, and reuses the pure poker brain
(backend/game/poker/{cards,evaluator,state,showdown}.py). Every seat is a HUMAN
— there are no bots. The server reconstructs the betting engine from DB rows on
every request (no in-memory game state), applies one action, advances streets /
runs out all-ins / resolves showdown, and persists back.

Design constraints (specs/holdem-multiplayer.md):
- Per-router SQL helpers at the bottom, prefixed `_`; lazy imports with noqa.
- Seat numbers on HoldemHand/HoldemHandSeat/HoldemAction are ENGINE indices
  (0..k-1 over the dealt-in players); HoldemSeat.seat_number is the physical
  chair. HoldemHandSeat.table_seat_number bridges the two.
- pot_total on the hand stores the engine's pot_committed (chips from completed
  streets only). The DISPLAY pot = pot_committed + sum(current street bets) is
  computed in the state payload, so the round-trip conserves chips.
- /state masks every seat's hole cards except the requesting viewer's while a
  hand is active; at showdown, non-folded seats are revealed and folded seats
  stay mucked.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

if TYPE_CHECKING:
    from collections.abc import Sequence

    from backend.game.poker.state import BettingState
    from backend.models import HoldemHand, HoldemHandSeat, HoldemSeat, HoldemTable

from backend.auth import CurrentUser
from backend.database import get_db
from backend.game.timer import is_expired, move_deadline
from backend.ratelimit import MUTATION_RATE_LIMIT, limiter
from backend.schemas import (
    HoldemActIn,
    HoldemJoinIn,
    HoldemSeatOut,
    HoldemTableCreateIn,
    HoldemTableListOut,
    HoldemTableOut,
    HoldemTableStateOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/holdem", tags=["holdem"])


# ─── Route handlers ───────────────────────────────────────────────────────────


@router.get("/tables", response_model=list[HoldemTableListOut])
async def list_tables(db: AsyncSession = Depends(get_db)) -> list[HoldemTableListOut]:
    """List all Hold'em tables with their seat counts."""
    return await _list_tables(db)


@router.post("/tables", response_model=HoldemTableOut, status_code=201)
@limiter.limit(MUTATION_RATE_LIMIT)
async def create_table(
    request: Request,
    body: HoldemTableCreateIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HoldemTableOut:
    """Create a new Hold'em cash table."""
    request.state.user_id = str(current_user)
    return await _create_table(body, db)


@router.post("/tables/{table_id}/join", response_model=HoldemSeatOut)
@limiter.limit(MUTATION_RATE_LIMIT)
async def join_table(
    request: Request,
    table_id: uuid.UUID,
    body: HoldemJoinIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HoldemSeatOut:
    """Take the lowest open seat and buy in for `buy_in` chips."""
    request.state.user_id = str(current_user)
    return await _join_seat(table_id, current_user, body.buy_in, db)


@router.post("/tables/{table_id}/leave")
@limiter.limit(MUTATION_RATE_LIMIT)
async def leave_table(
    request: Request,
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Leave the table: fold out of any active hand, cash the stack out to the
    bankroll, and free the seat."""
    request.state.user_id = str(current_user)
    await _leave_seat(table_id, current_user, db)
    return {"status": "ok"}


@router.get("/tables/{table_id}/state", response_model=HoldemTableStateOut)
async def get_table_state(
    request: Request,
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HoldemTableStateOut:
    """Polled state. Other players' hole cards are masked while a hand is live."""
    request.state.user_id = str(current_user)
    return await _build_state_payload(table_id, current_user, db)


@router.post("/tables/{table_id}/deal", response_model=HoldemTableStateOut)
@limiter.limit(MUTATION_RATE_LIMIT)
async def deal_hand(
    request: Request,
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HoldemTableStateOut:
    """Start the next hand. Idempotent — returns current state if a hand is
    already active. Any seated player may trigger it."""
    request.state.user_id = str(current_user)
    return await _deal_hand(table_id, current_user, db)


@router.post("/tables/{table_id}/act", response_model=HoldemTableStateOut)
@limiter.limit(MUTATION_RATE_LIMIT)
async def act(
    request: Request,
    table_id: uuid.UUID,
    body: HoldemActIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HoldemTableStateOut:
    """Submit your action (fold/check/call/raise/all_in). Turn-guarded."""
    request.state.user_id = str(current_user)
    return await _act(table_id, current_user, body, db)


# ─── Pure state↔DB bridge ─────────────────────────────────────────────────────


def _reconstruct_betting_state(hand: HoldemHand, hand_seats: Sequence[HoldemHandSeat]) -> BettingState:
    """Build a backend.game.poker.state.BettingState from DB rows. hand_seats
    are engine-indexed 0..k-1. `pot_committed` is hand.pot_total (completed
    streets only); per-seat current_bet carries the live street's chips."""
    from backend.game.poker.state import BettingState, Seat  # noqa: PLC0415

    by_num = {hs.seat_number: hs for hs in hand_seats}
    n = len(hand_seats)
    seat_objs = [
        Seat(
            seat_number=i,
            stack=by_num[i].final_stack,
            current_bet=by_num[i].current_bet,
            total_committed=by_num[i].contributed,
            is_folded=by_num[i].is_folded,
            is_all_in=by_num[i].is_all_in,
            has_acted_this_street=by_num[i].has_acted_this_street,
        )
        for i in range(n)
    ]
    return BettingState(
        seats=tuple(seat_objs),
        button_seat=hand.button_seat,
        small_blind=hand.small_blind,
        big_blind=hand.big_blind,
        ante=0,
        street=hand.street,
        current_bet_to_match=hand.current_bet_to_match,
        min_raise_increment=hand.min_raise_increment or hand.big_blind,
        last_aggressor_seat=hand.last_aggressor_seat,
        pot_committed=hand.pot_total,
    )


def _persist_state_to_hand(state: BettingState, hand: HoldemHand, hand_seats: Sequence[HoldemHandSeat]) -> None:
    """Sync BettingState back to DB rows. Stores the engine's pot_committed
    (completed streets) in hand.pot_total — NOT including live current bets, so
    the next reconstruction conserves chips."""
    hand.street = state.street
    hand.current_bet_to_match = state.current_bet_to_match
    hand.min_raise_increment = state.min_raise_increment
    hand.last_aggressor_seat = state.last_aggressor_seat
    hand.pot_total = state.pot_committed
    by_num = {hs.seat_number: hs for hs in hand_seats}
    for s in state.seats:
        hs = by_num.get(s.seat_number)
        if hs is None:
            continue
        hs.final_stack = s.stack
        hs.current_bet = s.current_bet
        hs.contributed = s.total_committed
        hs.is_folded = s.is_folded
        hs.is_all_in = s.is_all_in
        hs.has_acted_this_street = s.has_acted_this_street


def _set_move_deadline(hand: HoldemHand) -> None:
    """Keep `move_deadline_at` in lockstep with the turn pointer.

    Called immediately after every write to `current_to_act_seat`: a human on the
    clock gets a fresh 30s deadline; otherwise (all-in run-out, hand complete) the
    deadline is cleared. This is the load-bearing *deadline-iff-actor* invariant —
    a stale clock must never auto-act for a player who has no decision to make.
    """
    if hand.current_to_act_seat is not None:
        hand.move_deadline_at = move_deadline(datetime.now(timezone.utc))
    else:
        hand.move_deadline_at = None


def _deal_community_cards(state: BettingState, hand: HoldemHand, hand_seats: Sequence[HoldemHandSeat]) -> None:
    """Append flop (3) / turn (1) / river (1) to the board from the hand's
    stored deck, skipping cards already in play."""
    from backend.game.poker.cards import remove_cards  # noqa: PLC0415

    used = list(hand.board)
    for hs in hand_seats:
        used.extend(hs.hole_cards or [])
    remaining = remove_cards(list(hand.deck), used)
    if state.street == "flop":
        new_cards = remaining[:3]
    elif state.street in ("turn", "river"):
        new_cards = remaining[:1]
    else:
        new_cards = []
    hand.board = list(hand.board) + new_cards


def _showdown_board(hand: HoldemHand, hand_seats: Sequence[HoldemHandSeat]) -> list[dict]:
    """The board filled to 5 cards (deals the rest deterministically from the
    stored deck) — used when a hand reaches showdown before the river because
    everyone is all-in."""
    from backend.game.poker.cards import remove_cards  # noqa: PLC0415

    board = list(hand.board)
    if len(board) >= 5:
        return board
    used = list(board)
    for hs in hand_seats:
        used.extend(hs.hole_cards or [])
    remaining = remove_cards(list(hand.deck), used)
    return board + remaining[: 5 - len(board)]


# ─── SQL helpers (single source per router) ───────────────────────────────────


async def _list_tables(db: AsyncSession) -> list[HoldemTableListOut]:
    from sqlalchemy import func, select  # noqa: PLC0415

    from backend.models import HoldemSeat, HoldemTable  # noqa: PLC0415

    tables = (await db.execute(select(HoldemTable).order_by(HoldemTable.created_at))).scalars().all()
    out: list[HoldemTableListOut] = []
    for t in tables:
        seats_taken = (await db.execute(
            select(func.count(HoldemSeat.id)).where(HoldemSeat.table_id == t.id)
        )).scalar_one()
        out.append(HoldemTableListOut(
            id=t.id, name=t.name, small_blind=t.small_blind, big_blind=t.big_blind,
            min_buy_in=t.min_buy_in, max_buy_in=t.max_buy_in, max_seats=t.max_seats,
            status=t.status, seats_taken=seats_taken,
        ))
    return out


async def _create_table(body: HoldemTableCreateIn, db: AsyncSession) -> HoldemTableOut:
    from backend.models import HoldemTable  # noqa: PLC0415

    if body.small_blind <= 0:
        raise HTTPException(status_code=400, detail="small_blind must be positive")
    if body.big_blind < body.small_blind:
        raise HTTPException(status_code=400, detail="big_blind must be >= small_blind")
    if not (2 <= body.max_seats <= 9):
        raise HTTPException(status_code=400, detail="max_seats must be between 2 and 9")
    if body.min_buy_in <= 0 or body.max_buy_in < body.min_buy_in:
        raise HTTPException(status_code=400, detail="invalid buy-in range")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")

    table = HoldemTable(
        id=uuid.uuid4(),
        name=body.name.strip(),
        small_blind=body.small_blind,
        big_blind=body.big_blind,
        min_buy_in=body.min_buy_in,
        max_buy_in=body.max_buy_in,
        max_seats=body.max_seats,
        button_pos=None,
        status="waiting",
        created_at=datetime.now(timezone.utc),
    )
    db.add(table)
    await db.commit()
    await db.refresh(table)
    return HoldemTableOut.model_validate(table)


async def _join_seat(
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    buy_in: int,
    db: AsyncSession,
) -> HoldemSeatOut:
    from sqlalchemy import select  # noqa: PLC0415
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    from backend.models import HoldemSeat, HoldemTable, User  # noqa: PLC0415

    # Lock the table row FIRST (per-table serializer): serializes seat selection
    # against concurrent joins (no two callers grab the same open seat) and
    # against deal/leave.
    table = (await db.execute(
        select(HoldemTable).where(HoldemTable.id == table_id).with_for_update()
    )).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    # Idempotent: already seated → return existing seat.
    existing = (await db.execute(
        select(HoldemSeat).where(HoldemSeat.table_id == table_id, HoldemSeat.user_id == user_id)
    )).scalar_one_or_none()
    if existing is not None:
        return HoldemSeatOut.model_validate(existing)

    if not (table.min_buy_in <= buy_in <= table.max_buy_in):
        raise HTTPException(
            status_code=400,
            detail=f"Buy-in must be between {table.min_buy_in} and {table.max_buy_in}",
        )

    # Lock the user row before the balance check-then-debit so concurrent
    # buy-ins (e.g. to two tables at once) can't both pass the check and
    # double-debit. Mirrors the blackjack router's with_for_update discipline.
    user = (await db.execute(
        select(User).where(User.id == user_id).with_for_update()
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.chip_balance < buy_in:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient bankroll: have {user.chip_balance}, need {buy_in}",
        )

    occupied = {
        row[0]
        for row in (await db.execute(
            select(HoldemSeat.seat_number).where(HoldemSeat.table_id == table_id)
        )).fetchall()
    }
    open_seat = next((n for n in range(table.max_seats) if n not in occupied), None)
    if open_seat is None:
        raise HTTPException(status_code=409, detail="Table is full")

    user.chip_balance -= buy_in
    seat = HoldemSeat(
        id=uuid.uuid4(),
        table_id=table_id,
        user_id=user_id,
        seat_number=open_seat,
        stack=buy_in,
        status="active",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(seat)
    try:
        await db.commit()
    except IntegrityError:
        # Belt-and-suspenders behind the table lock: if a concurrent join still
        # grabbed this seat (or the user already has one), surface a clean 409
        # for the client to retry rather than an opaque 500.
        await db.rollback()
        raise HTTPException(status_code=409, detail="Seat just taken — please retry") from None
    await db.refresh(seat)
    return HoldemSeatOut.model_validate(seat)


async def _leave_seat(table_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> None:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import HoldemHand, HoldemHandSeat, HoldemSeat, HoldemTable, User  # noqa: PLC0415

    # Lock the table row FIRST (per-table serializer) so leave can't interleave
    # with a concurrent deal/join on the same table — the deal/leave interleave
    # is what would otherwise duplicate chips.
    table = (await db.execute(
        select(HoldemTable).where(HoldemTable.id == table_id).with_for_update()
    )).scalar_one_or_none()
    if table is None:
        return  # table gone — nothing to leave

    seat = (await db.execute(
        select(HoldemSeat)
        .where(HoldemSeat.table_id == table_id, HoldemSeat.user_id == user_id)
        .with_for_update()
    )).scalar_one_or_none()
    if seat is None:
        return  # idempotent — not seated

    hand = (await db.execute(
        select(HoldemHand)
        .where(HoldemHand.table_id == table_id, HoldemHand.status == "active")
        .with_for_update()
    )).scalar_one_or_none()
    hand_seats = []
    my_hs = None
    if hand is not None:
        hand_seats = (await db.execute(
            select(HoldemHandSeat).where(HoldemHandSeat.hand_id == hand.id).order_by(HoldemHandSeat.seat_number)
        )).scalars().all()
        my_hs = next((hs for hs in hand_seats if hs.user_id == user_id), None)

    if hand is not None and my_hs is not None and not my_hs.is_folded and my_hs.is_all_in:
        # All-in and fully committed: their chips are in the pot and they're
        # entitled to contest the showdown. We can't pull that equity mid-hand,
        # so don't fold or cash out — just sit them out so the NEXT deal skips
        # them. Their stake resolves into their seat stack at showdown; they
        # cash out with a later /leave once the hand is over.
        seat.status = "sitting_out"
        await db.commit()
        return

    if hand is not None and my_hs is not None:
        # In an active hand (live or already folded). Their live, uncommitted
        # stack lives on the hand-seat (the persistent seat still holds last
        # hand's total, updated only at showdown). Cash that out; chips already
        # committed to the pot stay there. Zero the hand-seat stack so the
        # engine doesn't double-count the uncommitted chips during the runout.
        uncommitted = my_hs.final_stack
        was_live = not my_hs.is_folded
        my_hs.is_folded = True
        my_hs.has_acted_this_street = True
        my_hs.final_stack = 0
        await db.flush()
        if was_live:
            # Folding a live player can close the street or end the hand —
            # advance so the table doesn't stall on the absent player.
            state = _reconstruct_betting_state(hand, hand_seats)
            await _advance_until_human_or_complete(state, hand, hand_seats, table, db)
        # The engine may refund this seat's UNCALLED bet during the runout
        # (advance_street returns the excess of a lone top bettor to its
        # bettor — even a folded one — before raking the pot). That refund
        # lands back on the hand-seat's final_stack via _persist_state_to_hand.
        # Cash out the uncommitted stack PLUS any such refund so the leaver
        # keeps chips that were never matched (chip conservation), instead of
        # the refund being stranded on a seat we are about to delete.
        cash_out = uncommitted + my_hs.final_stack
    else:
        # Not in an active hand — the persistent seat stack is the resolved stack.
        cash_out = seat.stack

    user = (await db.execute(
        select(User).where(User.id == user_id).with_for_update()
    )).scalar_one_or_none()
    if user is not None:
        user.chip_balance += cash_out

    await db.delete(seat)
    await db.commit()


async def _next_hand_number(table_id: uuid.UUID, db: AsyncSession) -> int:
    from sqlalchemy import func, select  # noqa: PLC0415

    from backend.models import HoldemHand  # noqa: PLC0415

    result = await db.execute(
        select(func.coalesce(func.max(HoldemHand.hand_number), 0)).where(HoldemHand.table_id == table_id)
    )
    return int(result.scalar_one()) + 1


async def _deal_hand(
    table_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> HoldemTableStateOut:
    from sqlalchemy import select  # noqa: PLC0415
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    from backend.game.poker.cards import create_deck  # noqa: PLC0415
    from backend.game.poker.state import create_state  # noqa: PLC0415
    from backend.models import (  # noqa: PLC0415
        HoldemHand,
        HoldemHandSeat,
        HoldemSeat,
        HoldemTable,
    )

    # Lock the table row FIRST (the per-table serializer). Critically this
    # serializes deal against a concurrent /leave: without it, leave could cash
    # a seated player's stack back to their bankroll while this deal has already
    # snapshotted that same stack into the new hand — duplicating chips.
    table = (await db.execute(
        select(HoldemTable).where(HoldemTable.id == table_id).with_for_update()
    )).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    seats = (await db.execute(
        select(HoldemSeat).where(HoldemSeat.table_id == table_id).order_by(HoldemSeat.seat_number)
    )).scalars().all()
    if not any(s.user_id == current_user for s in seats):
        raise HTTPException(status_code=403, detail="You are not seated at this table")

    # Idempotent: a hand is already in progress.
    active = (await db.execute(
        select(HoldemHand).where(HoldemHand.table_id == table_id, HoldemHand.status == "active")
    )).scalar_one_or_none()
    if active is not None:
        return await _build_state_payload(table_id, current_user, db)

    dealt = [s for s in seats if s.stack > 0 and s.status == "active"]
    if len(dealt) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 players with chips to deal")

    # Rotate the button to the next occupied chair clockwise.
    phys = [s.seat_number for s in dealt]
    if table.button_pos is None or table.button_pos not in phys:
        button_phys = phys[0]
    else:
        button_phys = phys[(phys.index(table.button_pos) + 1) % len(phys)]
    table.button_pos = button_phys
    button_idx = phys.index(button_phys)

    deck = create_deck()
    starting_stacks = [s.stack for s in dealt]
    state = create_state(
        starting_stacks=starting_stacks,
        button_seat=button_idx,
        small_blind=table.small_blind,
        big_blind=table.big_blind,
    )

    next_number = await _next_hand_number(table_id, db)
    hand = HoldemHand(
        id=uuid.uuid4(),
        table_id=table_id,
        hand_number=next_number,
        button_seat=button_idx,
        deck=deck,
        small_blind=table.small_blind,
        big_blind=table.big_blind,
        board=[],
        pot_total=state.pot_committed,
        side_pots=[],
        street=state.street,
        current_bet_to_match=state.current_bet_to_match,
        current_to_act_seat=None,
        last_aggressor_seat=state.last_aggressor_seat,
        min_raise_increment=state.min_raise_increment,
        status="active",
        result=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    try:
        await db.flush()
    except IntegrityError:
        # Another concurrent deal won the UNIQUE(table_id, hand_number) race.
        await db.rollback()
        return await _build_state_payload(table_id, current_user, db)

    hand_seats = []
    for i, src in enumerate(dealt):
        hs = HoldemHandSeat(
            id=uuid.uuid4(),
            hand_id=hand.id,
            seat_number=i,
            user_id=src.user_id,
            table_seat_number=src.seat_number,
            hole_cards=list(deck[i * 2:i * 2 + 2]),
            starting_stack=starting_stacks[i],
            final_stack=state.seats[i].stack,
            contributed=state.seats[i].total_committed,
            current_bet=state.seats[i].current_bet,
            is_folded=state.seats[i].is_folded,
            is_all_in=state.seats[i].is_all_in,
            has_acted_this_street=state.seats[i].has_acted_this_street,
        )
        hand_seats.append(hs)
        db.add(hs)

    table.status = "playing"
    await db.flush()

    # Persist the blind/ante posts the engine baked into create_state.
    await _record_action_log(state, hand, dealt, db)

    # Set whose turn it is (first to act), or run out / complete an all-in.
    await _advance_until_human_or_complete(state, hand, hand_seats, table, db)

    await db.commit()
    return await _build_state_payload(table_id, current_user, db)


async def _act(
    table_id: uuid.UUID,
    current_user: uuid.UUID,
    body: HoldemActIn,
    db: AsyncSession,
) -> HoldemTableStateOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.state import apply_action, next_to_act  # noqa: PLC0415
    from backend.models import HoldemHand, HoldemHandSeat, HoldemSeat, HoldemTable  # noqa: PLC0415

    # Lock the TABLE row first — it is the per-table serializer. Every mutating
    # holdem handler (deal/act/join/leave) locks the table row before any other,
    # so concurrent mutations on one table run strictly one-at-a-time (table →
    # hand/seat/user lock order, so no deadlock). SQLite ignores FOR UPDATE;
    # Postgres serializes.
    table = (await db.execute(
        select(HoldemTable).where(HoldemTable.id == table_id).with_for_update()
    )).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    if not (await db.execute(
        select(HoldemSeat.id).where(HoldemSeat.table_id == table_id, HoldemSeat.user_id == current_user)
    )).scalar_one_or_none():
        raise HTTPException(status_code=403, detail="You are not seated at this table")

    # Now that the caller is confirmed seated, resolve an expired turn first (the
    # timed-out actor may be THIS caller acting late, in which case they're
    # auto-folded/checked before their action is considered and the turn guard
    # below cleanly rejects it). Expiry is final.
    await _enforce_move_timeout(table_id, db)

    # Lock the active hand row for the transaction so two overlapping requests
    # (a double-submitted /act, or an /act racing a /leave) can't both pass the
    # turn guard against a stale snapshot and double-mutate. Mirrors the
    # blackjack router's with_for_update discipline (SQLite ignores it; Postgres
    # serializes). The second request re-reads after the first commits and is
    # cleanly rejected by the turn guard.
    hand = (await db.execute(
        select(HoldemHand)
        .where(HoldemHand.table_id == table_id, HoldemHand.status == "active")
        .with_for_update()
    )).scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=400, detail="No active hand; deal one first")

    hand_seats = (await db.execute(
        select(HoldemHandSeat).where(HoldemHandSeat.hand_id == hand.id).order_by(HoldemHandSeat.seat_number)
    )).scalars().all()
    my_hs = next((hs for hs in hand_seats if hs.user_id == current_user), None)
    if my_hs is None:
        raise HTTPException(status_code=400, detail="You are not in this hand")

    state = _reconstruct_betting_state(hand, hand_seats)
    if next_to_act(state) != my_hs.seat_number:
        raise HTTPException(status_code=400, detail="Not your turn")

    try:
        state = apply_action(state, my_hs.seat_number, body.action, body.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _persist_state_to_hand(state, hand, hand_seats)

    last_idx = await _last_action_index(hand.id, db)
    from backend.models import HoldemAction  # noqa: PLC0415

    # Log the chips actually PAID this action (the engine's current_bet delta),
    # not body.amount (which for a raise is the absolute raise-to level). This
    # keeps the action log's `amount` consistent with the blind/ante posts in
    # _record_action_log, so a replay UI can sum it without double-counting.
    last_rec = state.action_log[-1] if state.action_log else None
    db.add(HoldemAction(
        id=uuid.uuid4(),
        hand_id=hand.id,
        seat_number=my_hs.seat_number,
        user_id=current_user,
        action_index=last_idx + 1,
        street=last_rec.street if last_rec else hand.street,
        action=body.action,
        amount=last_rec.amount if last_rec else body.amount,
        created_at=datetime.now(timezone.utc),
    ))

    await _advance_until_human_or_complete(state, hand, hand_seats, table, db)

    await db.commit()
    return await _build_state_payload(table_id, current_user, db)


async def _enforce_move_timeout(table_id: uuid.UUID, db: AsyncSession) -> bool:
    """Lazily resolve an abandoned turn whose move clock has expired.

    Auto-action = the safest legal move: check if the actor faces no outstanding
    bet, otherwise fold. Returns True if a timeout fired. Double-checked locking:
    a cheap unlocked read short-circuits the common (not-expired) case; only when
    a deadline has actually passed do we take the per-table lock and re-validate,
    so two concurrent /state polls can't both resolve the same turn.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.state import apply_action  # noqa: PLC0415
    from backend.models import HoldemAction, HoldemHand, HoldemHandSeat, HoldemTable  # noqa: PLC0415

    # Cheap, unlocked pre-check.
    hand = (await db.execute(
        select(HoldemHand).where(HoldemHand.table_id == table_id, HoldemHand.status == "active")
    )).scalar_one_or_none()
    if hand is None or hand.current_to_act_seat is None:
        return False
    if not is_expired(hand.move_deadline_at, datetime.now(timezone.utc)):
        return False

    # Expired — take the per-table serializer and re-validate under the lock.
    table = (await db.execute(
        select(HoldemTable).where(HoldemTable.id == table_id).with_for_update()
    )).scalar_one_or_none()
    if table is None:
        return False
    hand = (await db.execute(
        select(HoldemHand)
        .where(HoldemHand.table_id == table_id, HoldemHand.status == "active")
        .with_for_update()
    )).scalar_one_or_none()
    if hand is None or hand.current_to_act_seat is None:
        return False
    if not is_expired(hand.move_deadline_at, datetime.now(timezone.utc)):
        return False  # a concurrent request already resolved it

    hand_seats = (await db.execute(
        select(HoldemHandSeat).where(HoldemHandSeat.hand_id == hand.id).order_by(HoldemHandSeat.seat_number)
    )).scalars().all()
    seat_num = hand.current_to_act_seat
    state = _reconstruct_betting_state(hand, hand_seats)
    seat = next((s for s in state.seats if s.seat_number == seat_num), None)
    if seat is None:
        return False

    action = "check" if state.current_bet_to_match <= seat.current_bet else "fold"
    state = apply_action(state, seat_num, action, 0)
    _persist_state_to_hand(state, hand, hand_seats)

    # Log the forced action so the replay/action-log stays complete. It is the
    # player's (involuntary) action, so it carries their user_id; the chips paid
    # (a fold/check pays 0) come from the engine's action_log for replay sums.
    last_idx = await _last_action_index(hand.id, db)
    last_rec = state.action_log[-1] if state.action_log else None
    actor_user_id = next((hs.user_id for hs in hand_seats if hs.seat_number == seat_num), None)
    db.add(HoldemAction(
        id=uuid.uuid4(),
        hand_id=hand.id,
        seat_number=seat_num,
        user_id=actor_user_id,
        action_index=last_idx + 1,
        street=last_rec.street if last_rec else hand.street,
        action=action,
        amount=last_rec.amount if last_rec else 0,
        created_at=datetime.now(timezone.utc),
    ))

    await _advance_until_human_or_complete(state, hand, hand_seats, table, db)
    return True


async def _advance_until_human_or_complete(
    state: BettingState,
    hand: HoldemHand,
    hand_seats: Sequence[HoldemHandSeat],
    table: HoldemTable,
    db: AsyncSession,
) -> None:
    """Drive the hand forward: deal streets when betting closes, run out the
    board when everyone is all-in, complete the hand at showdown / fold-out.
    Stops as soon as a human is next to act (every actor here is human)."""
    from backend.game.poker.state import advance_street, next_to_act, street_closed  # noqa: PLC0415

    max_iters = 32  # at most a handful of street transitions per hand
    for _ in range(max_iters):
        if street_closed(state):
            if state.street == "complete" or len(state.live_seats()) <= 1:
                await _complete_hand(state, hand, hand_seats, table, db)
                return
            state = advance_street(state)
            _deal_community_cards(state, hand, hand_seats)
            _persist_state_to_hand(state, hand, hand_seats)
            continue

        nxt = next_to_act(state)
        if nxt is None:
            break
        # Next actor is a human — stop and wait for their /act request.
        hand.current_to_act_seat = nxt
        _persist_state_to_hand(state, hand, hand_seats)
        _set_move_deadline(hand)
        return

    _persist_state_to_hand(state, hand, hand_seats)
    hand.current_to_act_seat = next_to_act(state)
    _set_move_deadline(hand)


async def _complete_hand(
    state: BettingState,
    hand: HoldemHand,
    hand_seats: Sequence[HoldemHandSeat],
    table: HoldemTable,
    db: AsyncSession,
) -> None:
    """Showdown / fold-out: fill the board, compute side pots, award, write
    stacks back to the persistent seats, mark the hand complete."""
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.state import advance_street, award_pots, compute_side_pots  # noqa: PLC0415
    from backend.game.poker.showdown import decide_winners_per_pot  # noqa: PLC0415
    from backend.models import HoldemSeat  # noqa: PLC0415

    while state.street != "complete":
        state = advance_street(state)

    live = state.live_seats()
    pots = compute_side_pots(state)

    if len(live) <= 1:
        winners_per_pot = [[live[0].seat_number] if live else [] for _ in pots]
    else:
        board = _showdown_board(hand, hand_seats)
        hand.board = board
        by_num = {hs.seat_number: hs for hs in hand_seats}
        hole_by_seat = {
            s.seat_number: list(by_num[s.seat_number].hole_cards)
            for s in live
            if s.seat_number in by_num and len(by_num[s.seat_number].hole_cards) == 2
        }
        winners_per_pot = decide_winners_per_pot(state, hole_by_seat, board)

    state = award_pots(state, winners_per_pot)
    _persist_state_to_hand(state, hand, hand_seats)
    hand.status = "complete"
    hand.street = "complete"
    hand.current_to_act_seat = None
    _set_move_deadline(hand)  # hand over → nobody on the clock
    hand.side_pots = [{"amount": amt, "eligible": list(elig)} for amt, elig in pots]
    hand.result = {
        "winners_per_pot": [list(w) for w in winners_per_pot],
        "side_pots": [{"amount": amt, "eligible": list(elig)} for amt, elig in pots],
    }

    # Write final stacks back to the persistent seats. Key on BOTH the physical
    # chair AND the user — a player can leave mid-hand and a new player can take
    # the vacated chair before this hand resolves; without the user_id guard
    # we'd clobber the new occupant's freshly bought-in stack (chip theft).
    seats = (await db.execute(
        select(HoldemSeat).where(HoldemSeat.table_id == table.id)
    )).scalars().all()
    seat_by_phys = {s.seat_number: s for s in seats}
    for hs in hand_seats:
        ps = seat_by_phys.get(hs.table_seat_number)
        if ps is not None and ps.user_id == hs.user_id:
            ps.stack = state.seats[hs.seat_number].stack

    table.status = "waiting"


async def _last_action_index(hand_id: uuid.UUID, db: AsyncSession) -> int:
    from sqlalchemy import func, select  # noqa: PLC0415

    from backend.models import HoldemAction  # noqa: PLC0415

    result = await db.execute(
        select(func.coalesce(func.max(HoldemAction.action_index), -1)).where(HoldemAction.hand_id == hand_id)
    )
    return int(result.scalar_one())


async def _record_action_log(
    state: BettingState,
    hand: HoldemHand,
    dealt: Sequence[HoldemSeat],
    db: AsyncSession,
) -> None:
    """Persist the action records the engine produced (blind + ante posts at
    deal). Engine seat index → posting user via the dealt list."""
    from backend.models import HoldemAction  # noqa: PLC0415

    last_idx = await _last_action_index(hand.id, db)
    for offset, rec in enumerate(state.action_log):
        user_id = dealt[rec.seat_number].user_id if rec.seat_number < len(dealt) else None
        db.add(HoldemAction(
            id=uuid.uuid4(),
            hand_id=hand.id,
            seat_number=rec.seat_number,
            user_id=user_id if rec.action not in ("post_blind", "post_ante") else None,
            action_index=last_idx + offset + 1,
            street=rec.street,
            action=rec.action,
            amount=rec.amount,
            created_at=datetime.now(timezone.utc),
        ))


async def _build_state_payload(
    table_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> HoldemTableStateOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import (  # noqa: PLC0415
        HoldemAction,
        HoldemHand,
        HoldemHandSeat,
        HoldemSeat,
        HoldemTable,
        User,
    )
    from backend.schemas import (  # noqa: PLC0415
        HoldemActionOut,
        HoldemHandSeatStateOut,
        HoldemHandStateOut,
        HoldemSeatOut,
        HoldemTableOut,
    )

    # Poll path drives lazy timeout enforcement — but ONLY for a SEATED caller.
    # /state is viewable by spectators ("you're watching"); a non-seated viewer
    # must not be able to mutate (drive) another table's game by polling it. A
    # seated player's poll resolves an abandoned turn.
    caller_seated = (await db.execute(
        select(HoldemSeat.id).where(HoldemSeat.table_id == table_id, HoldemSeat.user_id == current_user)
    )).scalar_one_or_none() is not None
    if caller_seated:
        await _enforce_move_timeout(table_id, db)

    table = (await db.execute(select(HoldemTable).where(HoldemTable.id == table_id))).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    seats = (await db.execute(
        select(HoldemSeat).where(HoldemSeat.table_id == table_id).order_by(HoldemSeat.seat_number)
    )).scalars().all()

    # Usernames for everyone seated + everyone in the latest hand.
    user_ids = {s.user_id for s in seats}

    latest = (await db.execute(
        select(HoldemHand)
        .where(HoldemHand.table_id == table_id)
        .order_by(HoldemHand.hand_number.desc())
        .limit(1)
    )).scalar_one_or_none()

    hand_seats = []
    actions = []
    if latest is not None:
        hand_seats = (await db.execute(
            select(HoldemHandSeat).where(HoldemHandSeat.hand_id == latest.id).order_by(HoldemHandSeat.seat_number)
        )).scalars().all()
        actions = (await db.execute(
            select(HoldemAction).where(HoldemAction.hand_id == latest.id).order_by(HoldemAction.action_index)
        )).scalars().all()
        user_ids.update(hs.user_id for hs in hand_seats)

    usernames: dict[uuid.UUID, str] = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            usernames[u.id] = u.username

    seats_out = [
        HoldemSeatOut(
            id=s.id, user_id=s.user_id, seat_number=s.seat_number, stack=s.stack,
            status=s.status, username=usernames.get(s.user_id),
        )
        for s in seats
    ]

    your_seat_number = None
    current_hand_payload = None
    if latest is not None:
        is_active = latest.status == "active"
        # A showdown only happens when ≥2 non-folded seats reach the end; an
        # uncontested win (everyone else folded) mucks — no cards revealed.
        went_to_showdown = (not is_active) and sum(1 for hs in hand_seats if not hs.is_folded) >= 2
        seat_payload = []
        for hs in hand_seats:
            if hs.user_id == current_user:
                your_seat_number = hs.seat_number
            # Masking: show own cards always; opponents only at a showdown if not folded.
            if hs.user_id == current_user:
                hole = list(hs.hole_cards)
            elif went_to_showdown and not hs.is_folded:
                hole = list(hs.hole_cards)
            else:
                hole = [None, None]
            seat_payload.append(HoldemHandSeatStateOut(
                seat_number=hs.seat_number,
                table_seat_number=hs.table_seat_number,
                user_id=hs.user_id,
                username=usernames.get(hs.user_id),
                hole_cards=hole,
                starting_stack=hs.starting_stack,
                final_stack=hs.final_stack,
                current_bet=hs.current_bet,
                is_folded=hs.is_folded,
                is_all_in=hs.is_all_in,
            ))

        display_pot = latest.pot_total + sum(hs.current_bet for hs in hand_seats)
        current_hand_payload = HoldemHandStateOut(
            id=latest.id,
            hand_number=latest.hand_number,
            button_seat=latest.button_seat,
            small_blind=latest.small_blind,
            big_blind=latest.big_blind,
            board=list(latest.board),
            pot_total=display_pot,
            side_pots=list(latest.side_pots or []),
            street=latest.street,
            current_bet_to_match=latest.current_bet_to_match,
            current_to_act_seat=latest.current_to_act_seat,
            last_aggressor_seat=latest.last_aggressor_seat,
            min_raise_increment=latest.min_raise_increment,
            move_deadline_at=latest.move_deadline_at,
            status=latest.status,
            result=latest.result,
            seats=seat_payload,
            actions=[HoldemActionOut.model_validate(a) for a in actions],
        )

    return HoldemTableStateOut(
        table=HoldemTableOut.model_validate(table),
        seats=seats_out,
        current_hand=current_hand_payload,
        your_seat_number=your_seat_number,
    )
