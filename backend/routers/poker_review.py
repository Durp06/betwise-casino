"""
routers/poker_review.py — compute-on-read equity-backed decision review.

Four GET endpoints (specs/poker-review-pr2.md LOCKED contract):

- GET /api/holdem/hands/{hand_id}/review            → HandReview (multiplayer)
- GET /api/holdem/tables/{table_id}/review          → GameReview (table visit)
- GET /api/poker/hands/{hand_id}/review             → HandReview (solo)
- GET /api/poker/tournaments/{tournament_id}/review → GameReview (tournament).
  The upgraded unified shape lives in routers/poker_game.py (it owns the existing
  path); the per-hand solo endpoint lives here.

No migration, no live-play changes: reviews are recomputed from already-stored
rows on every read. The pure assembly lives in backend/game/poker/review.py;
this router only loads rows, enforces access control, and shapes the response.

Access control: the caller must have held a seat in the hand/session, else 403.
Only the caller's OWN actions are graded. Multiplayer responses never include
opponent hole cards (range-based grading needs none).

Design constraints (CLAUDE.md): thin handlers + `_`-prefixed SQL helpers; SQL
centralized here; lazy imports with noqa; raise HTTPException, never bare.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import (
    GameReviewHandOut,
    GameReviewOut,
    HandReviewActionOut,
    HandReviewOut,
)

if TYPE_CHECKING:
    from backend.game.poker.review import HandReview, ReviewHandInput

logger = logging.getLogger(__name__)

router = APIRouter(tags=["poker_review"])

# Cap a Game Review at the most recent finished hands (PR2: v1 cap = 50).
_GAME_REVIEW_HAND_CAP = 50


# ─── Route handlers ───────────────────────────────────────────────────────────


@router.get("/holdem/hands/{hand_id}/review", response_model=HandReviewOut)
async def get_holdem_hand_review(
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HandReviewOut:
    """Equity-backed review of the caller's decisions in one finished hold'em hand."""
    return await _get_holdem_hand_review(hand_id, current_user, db)


@router.get("/holdem/tables/{table_id}/review", response_model=GameReviewOut)
async def get_holdem_table_review(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> GameReviewOut:
    """Session-level report card for the caller's current visit to a hold'em table."""
    return await _get_holdem_table_review(table_id, current_user, db)


@router.get("/poker/hands/{hand_id}/review", response_model=HandReviewOut)
async def get_poker_hand_review(
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HandReviewOut:
    """Equity-backed review of the caller's decisions in one finished solo hand."""
    return await _get_poker_hand_review(hand_id, current_user, db)


# ─── Pure shaping (HandReview dataclass → Out schema) ─────────────────────────


def _hand_review_to_out(review: HandReview) -> HandReviewOut:
    return HandReviewOut(
        hand_id=review.hand_id,
        game=review.game,  # type: ignore[arg-type]
        your_hole=[{"suit": c["suit"], "value": c["value"]} for c in review.your_hole],
        board=[{"suit": c["suit"], "value": c["value"]} for c in review.board],
        graded_count=review.graded_count,
        accuracy=review.accuracy,
        ev_lost_bb=review.ev_lost_bb,
        worst_action_index=review.worst_action_index,
        actions=[
            HandReviewActionOut(
                action_index=g.action_index,
                street=g.street,  # type: ignore[arg-type]
                action=g.action,
                amount_bb=g.amount_bb,
                verdict=g.verdict,  # type: ignore[arg-type]
                confidence_tier=g.confidence_tier,  # type: ignore[arg-type]
                recommended_action=g.recommended_action,
                equity=g.equity,
                required_equity=g.required_equity,
                ev_loss_bb=g.ev_loss_bb,
                explanation=g.explanation,
            )
            for g in review.actions
        ],
    )


def _game_review_to_out(
    scope: str,
    game: str,
    reviews: list[HandReview],
) -> GameReviewOut:
    from backend.game.poker.review import aggregate_game_review, worst_verdict  # noqa: PLC0415

    overall, total_ev, graded = aggregate_game_review(reviews)
    return GameReviewOut(
        scope=scope,  # type: ignore[arg-type]
        game=game,  # type: ignore[arg-type]
        overall_accuracy=overall,
        total_ev_lost_bb=total_ev,
        graded_count=graded,
        hands=[
            GameReviewHandOut(
                hand_id=r.hand_id,
                accuracy=r.accuracy,
                ev_lost_bb=r.ev_lost_bb,
                graded_count=r.graded_count,
                worst_verdict=worst_verdict(r),  # type: ignore[arg-type]
            )
            for r in reviews
        ],
    )


# ─── Holdem row-loading → ReviewHandInput ─────────────────────────────────────


def _build_holdem_input(hand, hand_seats, actions, current_user: uuid.UUID) -> ReviewHandInput:
    """Translate finished-hand DB rows into the pure ReviewHandInput. Hole cards
    of OTHER seats are dropped — only the caller's own are carried in."""
    from backend.game.poker.review import (  # noqa: PLC0415
        ReviewActionRow,
        ReviewHandInput,
        ReviewSeatRow,
    )

    hero_seat_num = next((hs.seat_number for hs in hand_seats if hs.user_id == current_user), None)
    hero_hole: tuple = ()
    seat_rows: list[ReviewSeatRow] = []
    for hs in sorted(hand_seats, key=lambda h: h.seat_number):
        is_hero = hs.user_id == current_user
        holes = tuple(hs.hole_cards) if is_hero and len(hs.hole_cards) == 2 else ()
        if is_hero:
            hero_hole = holes
        seat_rows.append(ReviewSeatRow(
            seat_number=hs.seat_number,
            starting_stack=hs.starting_stack,
            hole_cards=holes,
            is_hero=is_hero,
        ))

    action_rows = [
        ReviewActionRow(
            seat_number=a.seat_number,
            action=a.action,
            amount=a.amount,
            is_hero=(a.user_id == current_user and a.seat_number == hero_seat_num),
        )
        for a in actions
    ]

    return ReviewHandInput(
        hand_id=str(hand.id),
        game="holdem",
        big_blind=hand.big_blind,
        small_blind=hand.small_blind,
        button_seat=hand.button_seat,
        ante=0,
        board=tuple(hand.board),
        seats=tuple(seat_rows),
        actions=tuple(action_rows),
        hero_hole=hero_hole,
        n_seats=len(seat_rows),
        villain_ranges=None,  # multiplayer → default_range() per opponent
    )


# ─── Poker (solo) row-loading → ReviewHandInput ───────────────────────────────


def _build_poker_input(hand, hand_seats, actions, seats, current_user: uuid.UUID) -> ReviewHandInput:
    """Translate a finished solo hand into ReviewHandInput. Solo villains use the
    bot's archetype range when known (sharper equity vs bots)."""
    from backend.game.poker.equity import archetype_range, default_range  # noqa: PLC0415
    from backend.game.poker.archetypes import ARCHETYPE_REGISTRY  # noqa: PLC0415
    from backend.game.poker.review import (  # noqa: PLC0415
        ReviewActionRow,
        ReviewHandInput,
        ReviewSeatRow,
    )

    hero_seat_num = next((s.seat_number for s in seats if s.user_id == current_user), None)
    archetype_by_seat = {s.seat_number: s.archetype_name for s in seats}

    hero_hole: tuple = ()
    seat_rows: list[ReviewSeatRow] = []
    for hs in sorted(hand_seats, key=lambda h: h.seat_number):
        is_hero = hs.seat_number == hero_seat_num
        holes = tuple(hs.hole_cards) if is_hero and len(hs.hole_cards) == 2 else ()
        if is_hero:
            hero_hole = holes
        seat_rows.append(ReviewSeatRow(
            seat_number=hs.seat_number,
            starting_stack=hs.starting_stack,
            hole_cards=holes,
            is_hero=is_hero,
        ))

    # Villain ranges in seat order over the NON-hero seats; the assembly trims
    # them to the live-opponent count at each decision.
    villain_ranges: list = []
    for hs in sorted(hand_seats, key=lambda h: h.seat_number):
        if hs.seat_number == hero_seat_num:
            continue
        name = archetype_by_seat.get(hs.seat_number)
        if name and name in ARCHETYPE_REGISTRY:
            villain_ranges.append(archetype_range(ARCHETYPE_REGISTRY[name]))
        else:
            villain_ranges.append(default_range())

    action_rows = [
        ReviewActionRow(
            seat_number=a.seat_number,
            action=a.action,
            amount=a.amount,
            is_hero=(a.user_id == current_user and a.is_human and a.seat_number == hero_seat_num),
        )
        for a in actions
    ]

    return ReviewHandInput(
        hand_id=str(hand.id),
        game="poker",
        big_blind=hand.big_blind,
        small_blind=hand.small_blind,
        button_seat=hand.button_seat,
        ante=hand.ante,
        board=tuple(hand.board),
        seats=tuple(seat_rows),
        actions=tuple(action_rows),
        hero_hole=hero_hole,
        n_seats=len(seats),
        villain_ranges=tuple(villain_ranges) if villain_ranges else None,
    )


# ─── SQL helpers (single source per router) ───────────────────────────────────


async def _get_holdem_hand_review(
    hand_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> HandReviewOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.review import build_hand_review  # noqa: PLC0415
    from backend.models import HoldemAction, HoldemHand, HoldemHandSeat  # noqa: PLC0415

    hand = (await db.execute(
        select(HoldemHand).where(HoldemHand.id == hand_id)
    )).scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")

    hand_seats = (await db.execute(
        select(HoldemHandSeat).where(HoldemHandSeat.hand_id == hand.id).order_by(HoldemHandSeat.seat_number)
    )).scalars().all()
    if not any(hs.user_id == current_user for hs in hand_seats):
        raise HTTPException(status_code=403, detail="You did not hold a seat in this hand")

    actions = (await db.execute(
        select(HoldemAction).where(HoldemAction.hand_id == hand.id).order_by(HoldemAction.action_index)
    )).scalars().all()

    data = _build_holdem_input(hand, hand_seats, actions, current_user)
    return _hand_review_to_out(build_hand_review(data))


async def _get_holdem_table_review(
    table_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> GameReviewOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.review import build_hand_review  # noqa: PLC0415
    from backend.models import HoldemAction, HoldemHand, HoldemHandSeat, HoldemTable  # noqa: PLC0415

    table = (await db.execute(
        select(HoldemTable).where(HoldemTable.id == table_id)
    )).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    # NOTE: "table visit" boundary. There is no persisted sit-start marker tying a
    # hand to the caller's CURRENT tenure, so per PR2 we fall back to "every
    # finished hand at this table the caller held a HoldemHandSeat row for",
    # capped at the most recent _GAME_REVIEW_HAND_CAP. If the caller re-buys into
    # the same chair this can span more than the literal current sit; acceptable
    # for v1 (the field docs do not claim full coverage).
    finished_hands = (await db.execute(
        select(HoldemHand)
        .join(HoldemHandSeat, HoldemHandSeat.hand_id == HoldemHand.id)
        .where(
            HoldemHand.table_id == table_id,
            HoldemHand.status == "complete",
            HoldemHandSeat.user_id == current_user,
        )
        .order_by(HoldemHand.hand_number.desc())
        .limit(_GAME_REVIEW_HAND_CAP)
    )).scalars().all()

    if not finished_hands:
        # Caller never held a seat in a finished hand here → not a participant.
        seated = (await db.execute(
            select(HoldemHandSeat.id)
            .join(HoldemHand, HoldemHandSeat.hand_id == HoldemHand.id)
            .where(HoldemHand.table_id == table_id, HoldemHandSeat.user_id == current_user)
            .limit(1)
        )).scalar_one_or_none()
        if seated is None:
            raise HTTPException(status_code=403, detail="You have not held a seat at this table")

    reviews: list = []
    # Oldest-first in the response for stable reading order.
    for hand in sorted(finished_hands, key=lambda h: h.hand_number):
        hand_seats = (await db.execute(
            select(HoldemHandSeat).where(HoldemHandSeat.hand_id == hand.id).order_by(HoldemHandSeat.seat_number)
        )).scalars().all()
        actions = (await db.execute(
            select(HoldemAction).where(HoldemAction.hand_id == hand.id).order_by(HoldemAction.action_index)
        )).scalars().all()
        data = _build_holdem_input(hand, hand_seats, actions, current_user)
        reviews.append(build_hand_review(data))

    return _game_review_to_out("table_visit", "holdem", reviews)


async def _get_poker_hand_review(
    hand_id: uuid.UUID,
    current_user: uuid.UUID,
    db: AsyncSession,
) -> HandReviewOut:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.game.poker.review import build_hand_review  # noqa: PLC0415
    from backend.models import PokerAction, PokerHand, PokerHandSeat, PokerSeat  # noqa: PLC0415

    hand = (await db.execute(
        select(PokerHand).where(PokerHand.id == hand_id)
    )).scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")

    seats = (await db.execute(
        select(PokerSeat).where(PokerSeat.tournament_id == hand.tournament_id).order_by(PokerSeat.seat_number)
    )).scalars().all()
    if not any(s.user_id == current_user for s in seats):
        raise HTTPException(status_code=403, detail="Not a participant in this tournament")

    hand_seats = (await db.execute(
        select(PokerHandSeat).where(PokerHandSeat.hand_id == hand.id).order_by(PokerHandSeat.seat_number)
    )).scalars().all()
    actions = (await db.execute(
        select(PokerAction).where(PokerAction.hand_id == hand.id).order_by(PokerAction.action_index)
    )).scalars().all()

    data = _build_poker_input(hand, hand_seats, actions, seats, current_user)
    return _hand_review_to_out(build_hand_review(data))
