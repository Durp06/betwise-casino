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

from backend.auth import CurrentUser
from backend.database import get_db
from backend.schemas import ActionIn, DealIn, HandOut, HandReplayActionOut

router = APIRouter(tags=["game"])


# ─── Route handlers ───────────────────────────────────────────────────────────

@router.post("/tables/{table_id}/deal", response_model=HandOut)
async def deal(
    table_id: uuid.UUID,
    body: DealIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HandOut:
    """Create/join a betting session and deal initial cards."""
    return await _deal_hand(table_id, current_user, body.bet, db)


@router.post("/tables/{table_id}/action", response_model=HandOut)
async def take_action(
    table_id: uuid.UUID,
    body: ActionIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HandOut:
    """Take a game action (hit/stand/double/split)."""
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
    """Validate bet, create/join session, deal 2 cards to caller and 2 to dealer."""
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

    # Fetch user for chip balance check
    result = await db.execute(select(User).where(User.id == user_id))
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

    # Find or create a session in "betting" or "playing" phase.
    # Multiplayer: ALL seated players can deal into the same session, even
    # after the first player flipped status to "playing". The per-user
    # duplicate-hand guard below prevents double-dealing for the same user.
    # Rounds that have moved past play (dealer_turn / finished) don't match
    # this filter, so a fresh session is created — that's how replay works.
    result = await db.execute(
        select(GameSession).where(
            (GameSession.table_id == table_id)
            & (GameSession.status.in_(("betting", "playing")))
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        # Create a new session with a fresh deck
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

    # Check caller doesn't already have a hand in this session
    result = await db.execute(
        select(Hand).where(
            (Hand.session_id == session.id) & (Hand.user_id == user_id)
        )
    )
    existing_hand = result.scalar_one_or_none()
    if existing_hand is not None:
        # Return existing hand
        return HandOut(
            id=existing_hand.id,
            session_id=existing_hand.session_id,
            user_id=existing_hand.user_id,
            cards=existing_hand.cards,
            bet=existing_hand.bet,
            status=existing_hand.status,
            outcome=existing_hand.outcome,
            payout=existing_hand.payout,
        )

    # Deal 2 cards to caller
    deck = list(session.deck_state)
    card1, deck = eng.deal_card(deck)
    card2, deck = eng.deal_card(deck)
    player_cards = [card1, card2]

    # Deal 2 cards to dealer (if not already dealt)
    dealer_cards = list(session.dealer_cards)
    if not dealer_cards:
        d_card1, deck = eng.deal_card(deck)
        d_card2, deck = eng.deal_card(deck)
        # Dealer shows first card; second is hole card (stored but hidden)
        dealer_cards = [d_card1, d_card2]

    # Deduct bet from user balance
    user.chip_balance -= bet
    await db.flush()

    # Create hand
    hand = Hand(
        id=uuid.uuid4(),
        session_id=session.id,
        user_id=user_id,
        cards=player_cards,
        bet=bet,
        status="active",
        outcome=None,
        payout=None,
    )
    db.add(hand)

    # Update session: save dealer cards and remaining deck, advance to playing
    session.dealer_cards = dealer_cards
    session.deck_state = deck
    session.status = "playing"

    # Update table status
    table.status = "playing"

    await db.flush()
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
    from backend.models import GameSession, Hand, PlayerAction  # noqa: PLC0415
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

    await db.flush()
    await db.refresh(hand)

    # Advance turn if hand is no longer active
    if hand.status != "active":
        await game_state.advance_turn(session.id, db)

    return HandOut(
        id=hand.id,
        session_id=hand.session_id,
        user_id=hand.user_id,
        cards=hand.cards,
        bet=hand.bet,
        status=hand.status,
        outcome=hand.outcome,
        payout=hand.payout,
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
