"""
routers/game.py — Round-level game endpoints for BetWise Casino.

Design constraints (specs/betwise-casino.md §T12):
- Per-router SQL helpers at the bottom — no inlined SQL in handlers.
- POST /api/tables/{id}/deal creates a session + deals 2 cards per player and dealer.
- POST /api/tables/{id}/action validates turn, records action, calls advance_turn.
- GET /api/hands/{hand_id}/actions is the gold hand-replay endpoint.
- Hole card: during deal, dealer gets [visible_card, hidden_card]; hidden card
  is stored in deck_state[0] conventionally (revealed at dealer_turn).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from backend.auth import CurrentUser
from backend.database import get_db
from backend.ratelimit import MUTATION_RATE_LIMIT, limiter
from backend.schemas import ActionIn, DealIn, HandOut, HandReplayActionOut

router = APIRouter(tags=["game"])


# ─── Route handlers ───────────────────────────────────────────────────────────

@router.post("/tables/{table_id}/deal", response_model=HandOut)
@limiter.limit(MUTATION_RATE_LIMIT)
async def deal(
    request: Request,
    table_id: uuid.UUID,
    body: DealIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HandOut:
    """Create/join a betting session and deal initial cards."""
    request.state.user_id = str(current_user)
    return await _deal_hand(table_id, current_user, body.bet, db)


@router.post("/tables/{table_id}/action", response_model=HandOut)
@limiter.limit(MUTATION_RATE_LIMIT)
async def take_action(
    request: Request,
    table_id: uuid.UUID,
    body: ActionIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HandOut:
    """Take a game action (hit/stand/double/split)."""
    request.state.user_id = str(current_user)
    return await _take_action(table_id, current_user, body.action, db)


@router.get("/hands/{hand_id}/actions", response_model=list[HandReplayActionOut])
async def get_hand_actions(
    hand_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[HandReplayActionOut]:
    """Return ordered actions for a hand (gold: hand replay).

    Owning user can always read. Other users can only read after session is finished.
    """
    return await _get_hand_replay(hand_id, current_user, db)


# ─── SQL helpers ─────────────────────────────────────────────────────────────

async def _deal_hand(
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    bet: int,
    db: AsyncSession,
) -> HandOut:
    """Place a bet into the table's open betting round (no cards dealt yet).

    Multiplayer: bets are collected with the session in "betting"; the round is
    dealt to everyone together by state.maybe_start_round once all seated players
    have bet (or the betting window elapses). A single-seat table deals at once.
    Betting into an in-progress ("playing") round is rejected with 409.
    """
    from datetime import datetime, timezone  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import CasinoTable, TableSeat, GameSession, Hand, User  # noqa: PLC0415
    from backend.game import engine as eng  # noqa: PLC0415

    # Fetch table
    result = await db.execute(select(CasinoTable).where(CasinoTable.id == table_id))
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    # Verify caller is seated
    result = await db.execute(
        select(TableSeat).where(
            (TableSeat.table_id == table_id) & (TableSeat.user_id == user_id)
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="You are not seated at this table")

    # Fetch user for chip balance check — row-locked so two concurrent deals
    # by the same user (e.g. seated at two tables) can't both pass the balance
    # check and double-debit. Mirrors the double-down path and the holdem
    # buy-in; SQLite ignores FOR UPDATE, Postgres serializes.
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate bet
    if bet > user.chip_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Bet {bet} exceeds chip balance {user.chip_balance}",
        )
    if bet < table.min_bet:
        raise HTTPException(
            status_code=400,
            detail=f"Bet {bet} is below table minimum {table.min_bet}",
        )
    if bet > table.max_bet:
        raise HTTPException(
            status_code=400,
            detail=f"Bet {bet} is above table maximum {table.max_bet}",
        )

    # Find the table's open round. Betting is only allowed while a round is
    # COLLECTING bets ("betting"). Once it deals ("playing") the round is locked,
    # so a late bet is rejected — you're dealt in on the next hand. Rounds past
    # play (dealer_turn / finished) don't match, so the first bet opens a fresh
    # round. This "one open round at a time" rule is what stops co-players from
    # fragmenting into separate sessions (the multiplayer muddle).
    result = await db.execute(
        select(GameSession).where(
            (GameSession.table_id == table_id)
            & (GameSession.status.in_(("betting", "playing")))
        )
    )
    session = result.scalar_one_or_none()

    if session is not None and session.status == "playing":
        raise HTTPException(
            status_code=409,
            detail="Round already in progress — you'll be dealt in on the next hand.",
        )

    if session is None:
        # Open a new betting round with a fresh deck.
        deck = eng.create_deck()
        session = GameSession(
            id=uuid.uuid4(),
            table_id=table_id,
            game_type="blackjack",
            dealer_cards=[],
            deck_state=deck,
            status="betting",
            created_at=datetime.now(timezone.utc),
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)

    # Idempotent: if the caller already bet this round, return that hand
    # (double-click / network retry must not double-escrow).
    result = await db.execute(
        select(Hand).where(
            (Hand.session_id == session.id) & (Hand.user_id == user_id)
        )
    )
    existing_hand = result.scalar_one_or_none()
    if existing_hand is not None:
        return HandOut(
            id=existing_hand.id,
            session_id=existing_hand.session_id,
            user_id=existing_hand.user_id,
            cards=existing_hand.cards,
            bet=existing_hand.bet,
            status=existing_hand.status,
            outcome=existing_hand.outcome,
            payout=existing_hand.payout,
            move_deadline_at=existing_hand.move_deadline_at,
        )

    # Escrow the bet and record the hand with NO cards yet. The round deals all
    # players + the dealer together once everyone has bet (or the betting window
    # elapses) — see state.maybe_start_round. "Awaiting deal" is signalled by the
    # session being "betting"; an empty `cards` list is the per-hand marker.
    user.chip_balance -= bet
    hand = Hand(
        id=uuid.uuid4(),
        session_id=session.id,
        user_id=user_id,
        cards=[],
        bet=bet,
        status="active",
        outcome=None,
        payout=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    await db.flush()

    # Try to start the round. Deals immediately iff this bet completes the table
    # (a single-seat table, or the last seat to bet); otherwise stays "betting".
    from backend.game import state as game_state  # noqa: PLC0415

    await game_state.maybe_start_round(table_id, db)

    # Re-load the caller's hand — it may now hold dealt cards + a move deadline.
    await db.refresh(hand)

    return HandOut(
        id=hand.id,
        session_id=hand.session_id,
        user_id=hand.user_id,
        cards=hand.cards,
        bet=hand.bet,
        status=hand.status,
        outcome=hand.outcome,
        payout=hand.payout,
        move_deadline_at=hand.move_deadline_at,
    )


async def _take_action(
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    db: AsyncSession,
) -> HandOut:
    """Validate and apply a game action. Record to player_actions."""
    from datetime import datetime, timezone  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import GameSession, Hand, PlayerAction, TableSeat  # noqa: PLC0415
    from backend.game import engine as eng  # noqa: PLC0415
    from backend.game import strategy  # noqa: PLC0415
    from backend.game import state as game_state  # noqa: PLC0415

    # Find active session for this table
    result = await db.execute(
        select(GameSession).where(
            (GameSession.table_id == table_id)
            & (GameSession.status == "playing")
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="No active game session for this table")

    # Lazily resolve an expired turn before processing this action — but only when
    # the caller is SEATED, so a non-participant can't drive the game by POSTing.
    # If the caller is themselves the timed-out actor they're auto-stood first;
    # the turn guard below then rejects their late action (expiry is final).
    # Re-load the session afterwards — enforcement may have advanced it to the
    # dealer turn.
    caller_seated = (await db.execute(
        select(TableSeat.id).where(TableSeat.table_id == table_id, TableSeat.user_id == user_id)
    )).scalar_one_or_none() is not None
    if caller_seated:
        await game_state.enforce_timeout(table_id, db)
    result = await db.execute(
        select(GameSession).where(
            (GameSession.table_id == table_id)
            & (GameSession.status == "playing")
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="No active game session for this table")

    # Check it's this user's turn
    current_player = await game_state.get_current_player(session.id, db)
    if current_player is None or current_player.id != user_id:
        raise HTTPException(status_code=403, detail="It is not your turn")

    # Fetch caller's hand — row-locked for the duration of the transaction.
    # Under Postgres READ COMMITTED this prevents two concurrent requests from
    # the same user both passing the turn check and both mutating cards/deck.
    # SQLite (in-memory tests) silently ignores FOR UPDATE but serialises writes
    # anyway, so behaviour is unchanged in the test suite.
    result = await db.execute(
        select(Hand)
        .where((Hand.session_id == session.id) & (Hand.user_id == user_id))
        .with_for_update()
    )
    hand = result.scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")

    # Validate action legality
    if action == "double" and not eng.can_double(hand.cards):
        raise HTTPException(status_code=400, detail="Cannot double after hitting")
    if action == "split":
        raise HTTPException(
            status_code=501,
            detail=(
                "Split is a known limitation — schema has UNIQUE(session_id, user_id) "
                "on hands. Coming in a future migration."
            ),
        )

    # Deal a card if hitting or doubling
    deck = list(session.deck_state)
    dealer_cards = list(session.dealer_cards)
    # Use first dealer card as upcard (the face-up card)
    dealer_upcard = dealer_cards[0] if dealer_cards else {"suit": "spades", "value": "2"}

    # Compute optimal action (server-side, authoritative)
    opt = strategy.optimal_action(
        hand.cards,
        dealer_upcard,
        can_double=eng.can_double(hand.cards),
        can_split=eng.can_split(hand.cards),
    )
    was_correct = action == opt

    # Apply the action
    new_cards = list(hand.cards)
    if action in ("hit", "double"):
        if not deck:
            # Reshuffle a new deck if the deck is empty (edge case in tests)
            deck = eng.create_deck()
        new_card, deck = eng.deal_card(deck)
        new_cards.append(new_card)
        session.deck_state = deck

    # For double: double the bet and deduct original bet again from chip balance.
    # Lock the User row too so concurrent double requests can't both deduct.
    if action == "double":
        from backend.models import User  # noqa: PLC0415
        result = await db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        doubling_user = result.scalar_one_or_none()
        if doubling_user is not None:
            doubling_user.chip_balance -= hand.bet
        hand.bet *= 2

    # Decision #3: increment accuracy counters inside the locked transaction.
    # total_decisions increments once per recorded action (every non-split action).
    # correct_decisions increments only when was_correct is True.
    # total_hands increments once when the hand reaches a terminal status (not on active hits).
    #
    # For non-double actions (hit, stand), fetch the User row for counter updates.
    # For double, doubling_user is already locked above — reuse it.
    if action != "double":
        from backend.models import User  # noqa: PLC0415
        result = await db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        acting_user = result.scalar_one_or_none()
    else:
        acting_user = doubling_user  # already fetched above

    # Record to player_actions
    pa = PlayerAction(
        id=uuid.uuid4(),
        hand_id=hand.id,
        user_id=user_id,
        action=action,
        player_guess=action,
        optimal_action=opt,
        was_correct=was_correct,
        hand_snapshot=list(hand.cards),  # snapshot before the new card
        dealer_upcard=dealer_upcard,
        chipy_explanation=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(pa)

    # Update hand state
    hand.cards = new_cards

    if eng.is_bust(new_cards):
        hand.status = "bust"
    elif eng.is_blackjack(new_cards):
        hand.status = "blackjack"
    elif action == "stand":
        hand.status = "standing"
    elif action == "double":
        # After double: one card dealt then must stand
        hand.status = "standing"

    # Decision #3: increment accuracy counters after hand status is resolved.
    # total_decisions: +1 for every recorded action.
    # correct_decisions: +1 only when was_correct.
    # total_hands: +1 only when the hand reaches a terminal status this action.
    if acting_user is not None:
        acting_user.total_decisions += 1
        if was_correct:
            acting_user.correct_decisions += 1
        # Terminal statuses: bust, blackjack, standing, finished.
        # "active" means the player can still hit — do NOT increment total_hands.
        if hand.status != "active":
            acting_user.total_hands += 1

    await db.flush()
    await db.refresh(hand)

    # Advance turn if hand is no longer active; otherwise the player hit and is
    # still on the clock — reset their 30s deadline for the next decision.
    if hand.status != "active":
        await game_state.advance_turn(session.id, db)
    else:
        await game_state.stamp_current_deadline(session.id, db, force=True)

    return HandOut(
        id=hand.id,
        session_id=hand.session_id,
        user_id=hand.user_id,
        cards=hand.cards,
        bet=hand.bet,
        status=hand.status,
        outcome=hand.outcome,
        payout=hand.payout,
        move_deadline_at=hand.move_deadline_at,
    )


async def _get_hand_replay(
    hand_id: uuid.UUID,
    current_user_id: uuid.UUID,
    db: AsyncSession,
) -> list[HandReplayActionOut]:
    """Return ordered player_actions for a hand.

    Access rules:
    - Owner can always read.
    - Others can only read when the session is finished.
    """
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import Hand, GameSession, PlayerAction  # noqa: PLC0415

    # Fetch hand
    result = await db.execute(select(Hand).where(Hand.id == hand_id))
    hand = result.scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Hand not found")

    # Fetch session to check status
    result = await db.execute(select(GameSession).where(GameSession.id == hand.session_id))
    session = result.scalar_one_or_none()

    # Access control
    is_owner = hand.user_id == current_user_id
    session_finished = session is not None and session.status == "finished"

    if not is_owner and not session_finished:
        raise HTTPException(
            status_code=403,
            detail="Cannot view replay while session is in progress",
        )

    # Fetch actions ordered by created_at ascending
    result = await db.execute(
        select(PlayerAction)
        .where(PlayerAction.hand_id == hand_id)
        .order_by(PlayerAction.created_at)
    )
    actions = result.scalars().all()

    return [
        HandReplayActionOut(
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
        )
        for a in actions
    ]
