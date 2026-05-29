"""
routers/poker_game.py — Texas Hold'em game-action endpoints.

Endpoints:
- POST /api/poker/tournaments/{id}/deal — deal the next hand (idempotent if a
  hand is already in progress; returns the new hand state).
- POST /api/poker/tournaments/{id}/act  — submit the human's action; the
  server resolves all bot actions up to the next human decision point or
  hand end in one request (brief §4.8).
- GET  /api/poker/hands/{hand_id}/replay — finished-hand replay payload.
- GET  /api/poker/tournaments/{id}/review — chess.com-style session review.

Design constraints (specs/texas-holdem.md §AC-R5..R11):
- ALL hand state lives in the DB. The server reconstructs BettingState from
  PokerHand + PokerHandSeat + PokerAction rows on every request (brief §4.8).
- Hole cards are visible only to the seat's owner during play; replays after
  showdown are public.
- Bot decisions use archetypes.decide with the persisted hand seed so the
  whole replay is deterministic given (seed, human actions).
- Single _helper SQL functions at the bottom (CLAUDE.md rule).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import (
    PokerActIn,
    PokerActionOut,
    PokerHandReplayOut,
    PokerHandSeatStateOut,
    PokerHandStateOut,
    PokerReviewActionOut,
    PokerSeatOut,
    PokerSessionReviewOut,
    PokerTournamentOut,
    PokerTournamentStateOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/poker", tags=["poker_game"])


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/tournaments/{tournament_id}/deal", response_model=PokerTournamentStateOut)
async def deal_hand(
    tournament_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PokerTournamentStateOut:
    """Deal the next hand. Idempotent — returns the current hand if one is
    already active."""
    return await _deal_or_continue_hand(tournament_id, current_user, db)


@router.post("/tournaments/{tournament_id}/act", response_model=PokerTournamentStateOut)
async def act(
    tournament_id: uuid.UUID,
    body: PokerActIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PokerTournamentStateOut:
    """Submit the human's action; server resolves all bot actions up to the
    next human decision point or hand end. Returns updated state + the new
    action log entries since the last poll."""
    return await _apply_human_action_and_resolve_bots(tournament_id, current_user, body, db)


@router.get("/hands/{hand_id}/replay", response_model=PokerHandReplayOut)
async def get_replay(
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PokerHandReplayOut:
    """Replay payload — full action log + revealed hole cards for finished
    hands (per spec: owner during play, public after showdown)."""
    return await _get_hand_replay(hand_id, current_user, db)


@router.get("/tournaments/{tournament_id}/review", response_model=PokerSessionReviewOut)
async def get_review(
    tournament_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PokerSessionReviewOut:
    """Chess.com-style classified review of every human action in the
    tournament. Deterministic spots get EV-loss; heuristic spots get only
    principle notes."""
    return await _get_session_review(tournament_id, current_user, db)


# ─── Pure helpers (state↔DB) ──────────────────────────────────────────────────


def _reconstruct_betting_state(hand, hand_seats, n_seats: int):
    """Build a backend.game.poker.state.BettingState from DB rows."""
    from backend.game.poker.state import BettingState, Seat  # noqa: PLC0415

    seats_by_num = {hs.seat_number: hs for hs in hand_seats}
    seat_objs = []
    for i in range(n_seats):
        hs = seats_by_num.get(i)
        if hs is None:
            # Seat busted before this hand started — treat as folded zero-chip
            seat_objs.append(Seat(seat_number=i, stack=0, is_folded=True))
            continue
        seat_objs.append(Seat(
            seat_number=hs.seat_number,
            stack=hs.final_stack,
            current_bet=hs.current_bet,
            total_committed=hs.contributed,
            is_folded=hs.is_folded,
            is_all_in=hs.is_all_in,
            has_acted_this_street=hs.has_acted_this_street,
        ))
    return BettingState(
        seats=tuple(seat_objs),
        button_seat=hand.button_seat,
        small_blind=hand.small_blind,
        big_blind=hand.big_blind,
        ante=hand.ante,
        street=cast("any", hand.street),
        current_bet_to_match=hand.current_bet_to_match,
        min_raise_increment=hand.min_raise_increment or hand.big_blind,
        last_aggressor_seat=hand.last_aggressor_seat,
        pot_committed=hand.pot_total,
    )


def _persist_state_to_hand(state, hand, hand_seats) -> None:
    """Sync BettingState back to DB rows (mutates the SQLA objects)."""
    hand.street = state.street
    hand.current_bet_to_match = state.current_bet_to_match
    hand.min_raise_increment = state.min_raise_increment
    hand.last_aggressor_seat = state.last_aggressor_seat
    hand.pot_total = state.pot_committed + sum(s.current_bet for s in state.seats)
    seats_by_num = {hs.seat_number: hs for hs in hand_seats}
    for s in state.seats:
        hs = seats_by_num.get(s.seat_number)
        if hs is None:
            continue
        hs.final_stack = s.stack
        hs.current_bet = s.current_bet
        hs.contributed = s.total_committed
        hs.is_folded = s.is_folded
        hs.is_all_in = s.is_all_in
        hs.has_acted_this_street = s.has_acted_this_street


def _hand_str_for_seat(hole_cards):
    """Canonical hand-string from 2 card dicts."""
    from backend.game.poker.ranges import hand_str  # noqa: PLC0415

    return hand_str(
        hole_cards[0]["value"], hole_cards[0]["suit"],
        hole_cards[1]["value"], hole_cards[1]["suit"],
    )


# ─── SQL helpers (single source per router) ───────────────────────────────────


async def _deal_or_continue_hand(
    tournament_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> PokerTournamentStateOut:
    from sqlalchemy import select  # noqa: PLC0415
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    from backend.game.poker.cards import create_deck  # noqa: PLC0415
    from backend.game.poker.state import create_state, next_to_act  # noqa: PLC0415
    from backend.game.poker.tournament import current_level  # noqa: PLC0415
    from backend.models import (  # noqa: PLC0415
        PokerHand,
        PokerHandSeat,
        PokerSeat,
        PokerTournament,
    )

    tournament = (await db.execute(
        select(PokerTournament).where(PokerTournament.id == tournament_id)
    )).scalar_one_or_none()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    seats = (await db.execute(
        select(PokerSeat).where(PokerSeat.tournament_id == tournament_id).order_by(PokerSeat.seat_number)
    )).scalars().all()
    user_seat = next((s for s in seats if s.user_id == current_user), None)
    if user_seat is None:
        raise HTTPException(status_code=403, detail="Not a participant in this tournament")

    # If an active hand exists, return it (idempotent). Also covers the
    # case where a hand exists but isn't "active" status — any extant hand
    # at the current_hand_number means deal already happened.
    active = (await db.execute(
        select(PokerHand).where(
            PokerHand.tournament_id == tournament_id,
            PokerHand.status == "active",
        )
    )).scalar_one_or_none()
    if active is not None:
        return await _build_state_payload(tournament, seats, user_seat, db)

    # Tournament complete?
    live_seats = [s for s in seats if not s.is_bust]
    if len(live_seats) <= 1:
        tournament.status = "complete"
        await db.commit()
        return await _build_state_payload(tournament, seats, user_seat, db)

    # Deal a new hand.
    next_number = tournament.current_hand_number + 1
    sb, bb, ante = current_level(next_number, tournament.hands_per_level)
    hand_seed = (tournament.seed * 31 + next_number) & 0x7FFFFFFF
    deck = create_deck(seed=hand_seed)

    starting_stacks = [s.current_stack for s in seats]
    state = create_state(
        starting_stacks=starting_stacks,
        button_seat=tournament.button_seat,
        small_blind=sb,
        big_blind=bb,
        ante=ante,
    )

    # Deal 2 hole cards per LIVE seat (skip busted)
    hole_cards_per_seat: dict[int, list] = {}
    cursor = 0
    for s in seats:
        if s.is_bust:
            hole_cards_per_seat[s.seat_number] = []
            continue
        hole_cards_per_seat[s.seat_number] = list(deck[cursor:cursor + 2])
        cursor += 2

    # Create PokerHand row + PokerHandSeat rows
    hand = PokerHand(
        id=uuid.uuid4(),
        tournament_id=tournament_id,
        hand_number=next_number,
        button_seat=tournament.button_seat,
        seed=hand_seed,
        small_blind=sb,
        big_blind=bb,
        ante=ante,
        board=[],
        pot_total=state.pot_committed + sum(s.current_bet for s in state.seats),
        side_pots=[],
        street=state.street,
        current_bet_to_match=state.current_bet_to_match,
        current_to_act_seat=next_to_act(state),
        last_aggressor_seat=state.last_aggressor_seat,
        min_raise_increment=state.min_raise_increment,
        status="active",
        result=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    # Race-safe insert: under React StrictMode the deal endpoint can be
    # called twice in rapid succession. The first request wins; the second
    # hits the UNIQUE(tournament_id, hand_number) constraint. Catch it,
    # rollback our half-built state, and return the active hand the winner
    # created.
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # Re-read seats + active hand under a fresh session view
        tournament = (await db.execute(
            select(PokerTournament).where(PokerTournament.id == tournament_id)
        )).scalar_one()
        seats = (await db.execute(
            select(PokerSeat).where(PokerSeat.tournament_id == tournament_id).order_by(PokerSeat.seat_number)
        )).scalars().all()
        user_seat = next(s for s in seats if s.user_id == current_user)
        return await _build_state_payload(tournament, seats, user_seat, db)

    hand_seat_objs = []
    for st in state.seats:
        hs = PokerHandSeat(
            id=uuid.uuid4(),
            hand_id=hand.id,
            seat_number=st.seat_number,
            hole_cards=hole_cards_per_seat[st.seat_number],
            starting_stack=starting_stacks[st.seat_number],
            final_stack=st.stack,
            contributed=st.total_committed,
            current_bet=st.current_bet,
            is_folded=st.is_folded,
            is_all_in=st.is_all_in,
            has_acted_this_street=st.has_acted_this_street,
        )
        hand_seat_objs.append(hs)
        db.add(hs)

    # Bump hand counter
    tournament.current_hand_number = next_number
    await db.flush()

    # Persist initial action log (blind + ante posts)
    await _persist_action_records(state, hand, db, seats)

    # Drive bot actions up to next human decision (no human action submitted yet)
    await _drive_bot_actions(state, tournament, hand, hand_seat_objs, seats, db)

    await db.commit()
    return await _build_state_payload(tournament, seats, user_seat, db)


async def _apply_human_action_and_resolve_bots(
    tournament_id: uuid.UUID,
    current_user: uuid.UUID,
    body: PokerActIn,
    db: AsyncSession,
) -> PokerTournamentStateOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.oracle import DecisionSnapshot, classify_decision  # noqa: PLC0415
    from backend.game.poker.state import apply_action, next_to_act  # noqa: PLC0415
    from backend.game.poker.tournament import seat_position_label  # noqa: PLC0415
    from backend.models import (  # noqa: PLC0415
        PokerAction,
        PokerHand,
        PokerHandSeat,
        PokerSeat,
        PokerTournament,
    )

    tournament = (await db.execute(
        select(PokerTournament).where(PokerTournament.id == tournament_id)
    )).scalar_one_or_none()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    seats = (await db.execute(
        select(PokerSeat).where(PokerSeat.tournament_id == tournament_id).order_by(PokerSeat.seat_number)
    )).scalars().all()
    user_seat = next((s for s in seats if s.user_id == current_user), None)
    if user_seat is None:
        raise HTTPException(status_code=403, detail="Not a participant in this tournament")

    hand = (await db.execute(
        select(PokerHand).where(
            PokerHand.tournament_id == tournament_id,
            PokerHand.status == "active",
        )
    )).scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=400, detail="No active hand; deal one first")

    hand_seats = (await db.execute(
        select(PokerHandSeat).where(PokerHandSeat.hand_id == hand.id).order_by(PokerHandSeat.seat_number)
    )).scalars().all()
    state = _reconstruct_betting_state(hand, hand_seats, len(seats))

    next_seat = next_to_act(state)
    if next_seat != user_seat.seat_number:
        raise HTTPException(status_code=400, detail="Not your turn")

    # Build oracle snapshot BEFORE applying the action (so we capture the state
    # at the decision moment).
    user_hand_seat = next(hs for hs in hand_seats if hs.seat_number == user_seat.seat_number)
    hole = tuple(user_hand_seat.hole_cards)
    board_cards = tuple(hand.board)
    snap = DecisionSnapshot(
        hole=hole,
        board=board_cards,
        street=cast("any", hand.street),
        position=seat_position_label(user_seat.seat_number, hand.button_seat, len(seats)),
        hand_str=_hand_str_for_seat(user_hand_seat.hole_cards),
        stack_bb=user_hand_seat.final_stack / hand.big_blind if hand.big_blind else 0,
        pot_bb=hand.pot_total / hand.big_blind if hand.big_blind else 0,
        to_call_bb=(state.current_bet_to_match - user_hand_seat.current_bet) / hand.big_blind if hand.big_blind else 0,
        n_live_opponents=len([s for s in state.live_seats() if s.seat_number != user_seat.seat_number]),
        seats_remaining=len([s for s in seats if not s.is_bust]),
        is_bubble=_is_bubble_stage(seats, tournament),
        live_equity=None,  # the equity engine is too slow for the request path; oracle handles None
    )
    classification = classify_decision(snap, body.action, cast("any", tournament.advice_mode))

    # Apply human action
    state = apply_action(state, user_seat.seat_number, body.action, body.amount)
    _persist_state_to_hand(state, hand, hand_seats)

    # Record human action
    last_action_idx = (await _last_action_index(hand.id, db)) + 1
    db.add(PokerAction(
        id=uuid.uuid4(),
        hand_id=hand.id,
        seat_number=user_seat.seat_number,
        user_id=current_user,
        action_index=last_action_idx,
        street=hand.street,
        action=body.action,
        amount=body.amount,
        recommended_action=classification.recommended_action,
        confidence_tier=classification.confidence_tier,
        verdict=classification.verdict,
        ev_loss_chips=classification.ev_loss_chips,
        live_equity=None,
        chipy_explanation=classification.coach_summary,
        is_human=True,
        created_at=datetime.now(timezone.utc),
    ))

    # Update streak if deterministic
    if classification.counts_toward_streak:
        from backend.models import User  # noqa: PLC0415

        user_row = (await db.execute(select(User).where(User.id == current_user))).scalar_one_or_none()
        if user_row is not None:
            user_row.total_hands += 1
            if classification.correct:
                user_row.correct_decisions += 1
                user_row.current_streak += 1
                if user_row.current_streak > user_row.best_streak:
                    user_row.best_streak = user_row.current_streak
            else:
                user_row.current_streak = 0

    # Resolve street advancement, bots, and hand completion
    await _drive_bot_actions(state, tournament, hand, hand_seats, seats, db)

    await db.commit()
    return await _build_state_payload(tournament, seats, user_seat, db)


def _is_bubble_stage(seats, tournament) -> bool:
    """Heuristic: bubble = one elimination from the money."""
    from backend.game.poker.tournament import payout_pcts_for_seats  # noqa: PLC0415

    live = [s for s in seats if not s.is_bust]
    n_paid = len(payout_pcts_for_seats(len(seats)))
    return len(live) == n_paid + 1


async def _last_action_index(hand_id: uuid.UUID, db: AsyncSession) -> int:
    from sqlalchemy import func, select  # noqa: PLC0415

    from backend.models import PokerAction  # noqa: PLC0415

    result = await db.execute(
        select(func.coalesce(func.max(PokerAction.action_index), -1)).where(PokerAction.hand_id == hand_id)
    )
    return int(result.scalar_one())


async def _persist_action_records(state, hand, db, _seats) -> None:
    """Persist any action records from the initial create_state (blinds + antes)."""
    from backend.models import PokerAction  # noqa: PLC0415

    last_idx = await _last_action_index(hand.id, db)
    for i, rec in enumerate(state.action_log):
        db.add(PokerAction(
            id=uuid.uuid4(),
            hand_id=hand.id,
            seat_number=rec.seat_number,
            user_id=None,  # blind/ante posts aren't attributable to a user
            action_index=last_idx + i + 1,
            street=rec.street,
            action=rec.action,
            amount=rec.amount,
            recommended_action=None,
            confidence_tier=None,
            verdict=None,
            ev_loss_chips=None,
            live_equity=None,
            chipy_explanation=None,
            is_human=False,
            created_at=datetime.now(timezone.utc),
        ))


async def _drive_bot_actions(
    state,
    tournament,
    hand,
    hand_seats,
    seats,
    db: AsyncSession,
) -> None:
    """Resolve all bot actions until either a human is next or hand is complete.

    Also handles street advancement and hand completion (showdown, side pots,
    awarding chips, dealing next hand)."""
    import random as _random  # noqa: PLC0415

    from backend.game.poker.archetypes import (  # noqa: PLC0415
        ARCHETYPE_REGISTRY,
        ArchetypeContext,
        decide,
    )
    from backend.game.poker.state import (  # noqa: PLC0415
        advance_street,
        apply_action,
        next_to_act,
        street_closed,
    )
    from backend.models import PokerAction  # noqa: PLC0415

    seat_to_user_id = {s.seat_number: s.user_id for s in seats}
    seat_to_archetype = {s.seat_number: s.archetype_name for s in seats}
    rng = _random.Random(hand.seed)

    # Loop: as long as the hand is active and the next-to-act is a bot,
    # drive bot actions. When a street closes, advance + deal community cards.
    max_iters = 200  # safety cap
    for _ in range(max_iters):
        if street_closed(state):
            if state.street == "complete" or len(state.live_seats()) <= 1:
                await _complete_hand(state, hand, hand_seats, seats, tournament, db)
                return
            # Advance street + deal community cards
            state = advance_street(state)
            await _deal_community_cards(state, hand, hand_seats, db)
            _persist_state_to_hand(state, hand, hand_seats)
            hand.board = list(hand.board)  # ensure JSON tracking
            hand.current_to_act_seat = next_to_act(state)
            continue

        next_seat = next_to_act(state)
        if next_seat is None:
            break

        user_id_for_seat = seat_to_user_id.get(next_seat)
        if user_id_for_seat is not None:
            # Human's turn — stop here
            hand.current_to_act_seat = next_seat
            _persist_state_to_hand(state, hand, hand_seats)
            return

        # Bot's turn
        archetype_name = seat_to_archetype.get(next_seat)
        if archetype_name is None or archetype_name not in ARCHETYPE_REGISTRY:
            # Default: fold (shouldn't happen but defensive)
            state = apply_action(state, next_seat, "fold")
            continue

        spec = ARCHETYPE_REGISTRY[archetype_name]
        bot_seat_row = next(hs for hs in hand_seats if hs.seat_number == next_seat)
        hole_tuple = tuple(bot_seat_row.hole_cards) if len(bot_seat_row.hole_cards) == 2 else (
            {"suit": "hearts", "value": "2"}, {"suit": "spades", "value": "2"}
        )
        ctx = ArchetypeContext(
            hole=hole_tuple,
            board=tuple(hand.board),
            street=cast("any", state.street),
            position="MP",  # simplification — could compute via seat_position_label
            stack_bb=bot_seat_row.final_stack / hand.big_blind if hand.big_blind else 0,
            pot_bb=hand.pot_total / hand.big_blind if hand.big_blind else 0,
            to_call_bb=(state.current_bet_to_match - bot_seat_row.current_bet) / hand.big_blind if hand.big_blind else 0,
            n_live_opponents=max(0, len(state.live_seats()) - 1),
        )
        decision = decide(spec, ctx, rng)
        bot_action = decision.action

        # Translate raise_to_bb → raise_to chips amount when needed
        amount = 0
        if bot_action == "raise":
            amount = max(int(decision.raise_to_bb * hand.big_blind), state.current_bet_to_match + state.min_raise_increment)
        try:
            state = apply_action(state, next_seat, bot_action, amount)
        except ValueError:
            # Fall back to check/call/fold on illegal raise
            to_call = state.current_bet_to_match - state.seats[next_seat].current_bet
            if to_call > 0:
                state = apply_action(state, next_seat, "call")
                bot_action = "call"
            else:
                state = apply_action(state, next_seat, "check")
                bot_action = "check"
            amount = 0

        # Persist bot action record
        last_idx = await _last_action_index(hand.id, db)
        db.add(PokerAction(
            id=uuid.uuid4(),
            hand_id=hand.id,
            seat_number=next_seat,
            user_id=None,
            action_index=last_idx + 1,
            street=hand.street,
            action=bot_action,
            amount=amount,
            recommended_action=None,
            confidence_tier=None,
            verdict=None,
            ev_loss_chips=None,
            live_equity=None,
            chipy_explanation=decision.coach_note,
            is_human=False,
            created_at=datetime.now(timezone.utc),
        ))

    _persist_state_to_hand(state, hand, hand_seats)
    hand.current_to_act_seat = next_to_act(state)


async def _deal_community_cards(state, hand, hand_seats, db) -> None:
    """Deal flop (3), turn (1), or river (1) based on state.street."""
    from backend.game.poker.cards import create_deck, remove_cards  # noqa: PLC0415

    # Reconstruct used cards
    used = list(hand.board)
    for hs in hand_seats:
        for c in hs.hole_cards or []:
            used.append(c)
    deck = remove_cards(create_deck(seed=hand.seed), used)
    if state.street == "flop":
        new_cards = deck[:3]
    elif state.street in ("turn", "river"):
        new_cards = deck[:1]
    else:
        new_cards = []
    hand.board = list(hand.board) + new_cards


async def _complete_hand(state, hand, hand_seats, seats, tournament, db) -> None:
    """Run showdown if multiple seats are live, compute side pots, award,
    update PokerSeat current_stack, mark hand complete, rotate button."""
    from backend.game.poker.evaluator import best_5_of_7  # noqa: PLC0415
    from backend.game.poker.state import (  # noqa: PLC0415
        advance_street,
        award_pots,
        compute_side_pots,
    )
    from backend.game.poker.tournament import next_button  # noqa: PLC0415

    # If still on a betting street with only one live seat, fast-forward
    # everything into pot_committed.
    while state.street != "complete":
        state = advance_street(state)
        if state.street == "complete":
            break

    live = state.live_seats()
    pots = compute_side_pots(state)

    if len(live) == 1:
        # Only winner — gets all pots
        winners_per_pot = [[live[0].seat_number] for _ in pots]
    else:
        # Showdown — evaluate each live seat's best 5-of-7
        hand_seats_by_num = {hs.seat_number: hs for hs in hand_seats}
        board = list(hand.board)
        # Fill board to 5 cards (in case hand ended before river by all-in)
        # by dealing remaining community cards deterministically from the seed.
        if len(board) < 5:
            from backend.game.poker.cards import create_deck, remove_cards  # noqa: PLC0415

            used = list(board)
            for hs in hand_seats:
                for c in hs.hole_cards or []:
                    used.append(c)
            deck_remaining = remove_cards(create_deck(seed=hand.seed), used)
            needed = 5 - len(board)
            board = board + deck_remaining[:needed]
            hand.board = board

        ranks_by_seat = {}
        for s in live:
            hs = hand_seats_by_num.get(s.seat_number)
            if hs is None or len(hs.hole_cards) != 2:
                continue
            ranks_by_seat[s.seat_number] = best_5_of_7(list(hs.hole_cards) + board)

        winners_per_pot = []
        for _, eligible in pots:
            # Among eligible seats that are also live, find max
            candidates = [i for i in eligible if i in ranks_by_seat]
            if not candidates:
                winners_per_pot.append([])
                continue
            max_key = max(ranks_by_seat[i].cmp_key() for i in candidates)
            winners_per_pot.append([i for i in candidates if ranks_by_seat[i].cmp_key() == max_key])

    state = award_pots(state, winners_per_pot)
    _persist_state_to_hand(state, hand, hand_seats)
    hand.status = "complete"
    hand.street = "complete"
    hand.current_to_act_seat = None
    hand.result = {
        "winners_per_pot": [list(w) for w in winners_per_pot],
        "side_pots": [{"amount": amt, "eligible": list(elig)} for amt, elig in pots],
    }

    # Update each PokerSeat.current_stack from the final BettingState
    seats_by_num = {s.seat_number: s for s in seats}
    for st in state.seats:
        ps = seats_by_num.get(st.seat_number)
        if ps is None:
            continue
        ps.current_stack = st.stack
        if ps.current_stack <= 0 and not ps.is_bust:
            ps.is_bust = True
            live_after = [s for s in seats if not s.is_bust and s.seat_number != st.seat_number]
            ps.bust_position = len(live_after) + 1

    # Rotate button to next non-bust seat
    live_idx = [s.seat_number for s in seats if not s.is_bust]
    if len(live_idx) >= 2:
        tournament.button_seat = next_button(tournament.button_seat, live_idx)

    # If only one or zero seats left, mark tournament complete + payouts
    live_after = [s for s in seats if not s.is_bust]
    if len(live_after) <= 1:
        await _finalize_payouts(tournament, seats, db)


async def _finalize_payouts(tournament, seats, db) -> None:
    """Credit prize-pool back to bankrolls per finish order."""
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.tournament import payout_chips  # noqa: PLC0415
    from backend.models import User  # noqa: PLC0415

    tournament.status = "complete"
    prize_pool = tournament.buy_in_cents * (1 + tournament.bot_count)
    payouts = payout_chips(prize_pool, len(seats))

    # Determine finish order: highest bust_position is 1st (or non-bust if any).
    sorted_seats = sorted(
        seats,
        key=lambda s: (0 if not s.is_bust else 1, -(s.bust_position or 0), s.current_stack),
    )
    for idx, seat in enumerate(sorted_seats):
        if seat.user_id is None:
            continue
        if idx < len(payouts) and payouts[idx] > 0:
            user = (await db.execute(select(User).where(User.id == seat.user_id))).scalar_one_or_none()
            if user is not None:
                user.chip_balance += payouts[idx]


async def _build_state_payload(
    tournament,
    seats,
    user_seat,
    db: AsyncSession,
) -> PokerTournamentStateOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import PokerAction, PokerHand, PokerHandSeat  # noqa: PLC0415

    active = (await db.execute(
        select(PokerHand)
        .where(PokerHand.tournament_id == tournament.id)
        .order_by(PokerHand.hand_number.desc())
        .limit(1)
    )).scalar_one_or_none()

    current_hand_payload = None
    if active is not None:
        hand_seats = (await db.execute(
            select(PokerHandSeat).where(PokerHandSeat.hand_id == active.id).order_by(PokerHandSeat.seat_number)
        )).scalars().all()
        actions = (await db.execute(
            select(PokerAction).where(PokerAction.hand_id == active.id).order_by(PokerAction.action_index)
        )).scalars().all()

        # Mask hole cards for non-self seats while hand is active.
        seat_payload = []
        for hs in hand_seats:
            hole = hs.hole_cards
            if active.status == "active" and hs.seat_number != user_seat.seat_number:
                hole = [None, None]
            seat_payload.append(PokerHandSeatStateOut(
                seat_number=hs.seat_number,
                hole_cards=hole,
                starting_stack=hs.starting_stack,
                final_stack=hs.final_stack,
                current_bet=hs.current_bet,
                is_folded=hs.is_folded,
                is_all_in=hs.is_all_in,
            ))

        current_hand_payload = PokerHandStateOut(
            id=active.id,
            hand_number=active.hand_number,
            button_seat=active.button_seat,
            small_blind=active.small_blind,
            big_blind=active.big_blind,
            ante=active.ante,
            board=list(active.board),
            pot_total=active.pot_total,
            side_pots=list(active.side_pots or []),
            street=active.street,
            current_bet_to_match=active.current_bet_to_match,
            current_to_act_seat=active.current_to_act_seat,
            last_aggressor_seat=active.last_aggressor_seat,
            min_raise_increment=active.min_raise_increment,
            status=active.status,
            seats=seat_payload,
            actions=[PokerActionOut.model_validate(a) for a in actions],
        )

    return PokerTournamentStateOut(
        tournament=PokerTournamentOut.model_validate(tournament),
        seats=[PokerSeatOut.model_validate(s) for s in seats],
        current_hand=current_hand_payload,
        your_seat_number=user_seat.seat_number,
    )


async def _get_hand_replay(
    hand_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> PokerHandReplayOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import PokerAction, PokerHand, PokerHandSeat, PokerSeat  # noqa: PLC0415

    hand = (await db.execute(
        select(PokerHand).where(PokerHand.id == hand_id)
    )).scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")

    # Authorization: owner during play, public after.
    if hand.status != "complete":
        user_seats = (await db.execute(
            select(PokerSeat).where(
                PokerSeat.tournament_id == hand.tournament_id,
                PokerSeat.user_id == current_user,
            )
        )).scalars().all()
        if not user_seats:
            raise HTTPException(status_code=403, detail="Not a participant; replay available after showdown")

    hand_seats = (await db.execute(
        select(PokerHandSeat).where(PokerHandSeat.hand_id == hand.id).order_by(PokerHandSeat.seat_number)
    )).scalars().all()
    actions = (await db.execute(
        select(PokerAction).where(PokerAction.hand_id == hand.id).order_by(PokerAction.action_index)
    )).scalars().all()

    return PokerHandReplayOut(
        hand_id=hand.id,
        hand_number=hand.hand_number,
        seed=hand.seed,
        button_seat=hand.button_seat,
        board=list(hand.board),
        seats=[PokerHandSeatStateOut(
            seat_number=hs.seat_number,
            hole_cards=hs.hole_cards,
            starting_stack=hs.starting_stack,
            final_stack=hs.final_stack,
            current_bet=hs.current_bet,
            is_folded=hs.is_folded,
            is_all_in=hs.is_all_in,
        ) for hs in hand_seats],
        actions=[PokerActionOut.model_validate(a) for a in actions],
        result=hand.result,
    )


async def _get_session_review(
    tournament_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> PokerSessionReviewOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import PokerAction, PokerHand, PokerSeat, PokerTournament  # noqa: PLC0415

    tournament = (await db.execute(
        select(PokerTournament).where(PokerTournament.id == tournament_id)
    )).scalar_one_or_none()
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    user_seat = (await db.execute(
        select(PokerSeat).where(
            PokerSeat.tournament_id == tournament_id,
            PokerSeat.user_id == current_user,
        )
    )).scalar_one_or_none()
    if user_seat is None:
        raise HTTPException(status_code=403, detail="Not a participant")

    actions = (await db.execute(
        select(PokerAction, PokerHand.hand_number)
        .join(PokerHand, PokerAction.hand_id == PokerHand.id)
        .where(
            PokerHand.tournament_id == tournament_id,
            PokerAction.user_id == current_user,
            PokerAction.is_human == True,  # noqa: E712
        )
        .order_by(PokerHand.hand_number, PokerAction.action_index)
    )).all()

    review_rows: list[PokerReviewActionOut] = []
    total = 0
    det = 0
    correct = 0
    ev_lost = 0
    for action_row, hand_number in actions:
        total += 1
        if action_row.confidence_tier == "DETERMINISTIC":
            det += 1
            if action_row.verdict == "best":
                correct += 1
            ev_lost += action_row.ev_loss_chips or 0
        review_rows.append(PokerReviewActionOut(
            id=action_row.id,
            hand_number=hand_number,
            street=action_row.street,
            action=action_row.action,
            recommended_action=action_row.recommended_action,
            confidence_tier=action_row.confidence_tier,
            verdict=action_row.verdict,
            ev_loss_chips=action_row.ev_loss_chips,
            principle_note=action_row.chipy_explanation,
        ))

    return PokerSessionReviewOut(
        tournament_id=tournament_id,
        total_actions=total,
        deterministic_actions=det,
        optimal_count=correct,
        ev_lost_chips=ev_lost,
        actions=review_rows,
    )
