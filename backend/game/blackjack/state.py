"""
state.py — Game state machine for BetWise Casino blackjack.

Design constraints (specs/betwise-casino.md §T7):
- Async functions that take an AsyncSession.
- resolve_hand is a pure function (no DB) for easy unit testing.
- run_dealer hits until hard 17+ (dealer hits soft 17).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.game.blackjack import engine as eng


# ─── Pure resolution ─────────────────────────────────────────────────────────

def resolve_hand(
    hand: dict,
    dealer_cards: list[dict],
) -> tuple[str, int]:
    """Resolve a hand against the dealer.

    Parameters
    ----------
    hand : dict with keys "cards", "bet", "status"
    dealer_cards : list of card dicts (full dealer hand)

    Returns
    -------
    (outcome, payout) where outcome ∈ {"blackjack","win","push","loss","bust"}
    and payout is integer chips returned to the player.
    """
    cards = hand["cards"]
    bet = hand["bet"]
    status = hand.get("status", "active")

    # Already-busted hand
    if status == "bust" or eng.is_bust(cards):
        return ("bust", 0)

    # Player blackjack
    if status == "blackjack" or eng.is_blackjack(cards):
        # Dealer blackjack → push
        if eng.is_blackjack(dealer_cards):
            return ("push", bet)
        return ("blackjack", bet * 5 // 2)

    player_val = eng.hand_value(cards)
    dealer_val = eng.hand_value(dealer_cards)

    # Dealer bust → player wins
    if eng.is_bust(dealer_cards):
        return ("win", bet * 2)

    if player_val > dealer_val:
        return ("win", bet * 2)
    elif player_val == dealer_val:
        return ("push", bet)
    else:
        return ("loss", 0)


# ─── DB-backed state helpers ─────────────────────────────────────────────────

async def get_current_player(session_id: uuid.UUID, db: AsyncSession):
    """Return the first User whose Hand.status == 'active' in seat order, or None.

    Uses LEFT JOIN on table_seats so that tests without seeded seats still work.
    Falls back to ordering by hand creation if no seat data is available.
    """
    from backend.models import Hand, TableSeat, GameSession, User  # noqa: PLC0415

    # Get the game session to find the table
    result = await db.execute(select(GameSession).where(GameSession.id == session_id))
    game_session = result.scalar_one_or_none()
    if not game_session:
        return None

    # Get active hands — use outerjoin with seats for ordering when available.
    # COALESCE(seat_number, 999) puts unseated hands last.
    stmt = (
        select(Hand)
        .outerjoin(
            TableSeat,
            (TableSeat.user_id == Hand.user_id) & (TableSeat.table_id == game_session.table_id)
        )
        .where(Hand.session_id == session_id)
        .where(Hand.status == "active")
        .order_by(TableSeat.seat_number.asc().nullslast())
    )
    result = await db.execute(stmt)
    hand = result.scalars().first()
    if not hand:
        return None

    result = await db.execute(select(User).where(User.id == hand.user_id))
    return result.scalar_one_or_none()


async def advance_turn(session_id: uuid.UUID, db: AsyncSession) -> None:
    """Mark the next active player's turn, or trigger dealer play if no active players."""
    from backend.models import GameSession  # noqa: PLC0415

    next_player = await get_current_player(session_id, db)
    if next_player is None:
        # No more active players — trigger dealer turn
        result = await db.execute(select(GameSession).where(GameSession.id == session_id))
        game_session = result.scalar_one_or_none()
        if game_session and game_session.status == "playing":
            game_session.status = "dealer_turn"
            await db.flush()
            await run_dealer(session_id, db)


async def run_dealer(session_id: uuid.UUID, db: AsyncSession) -> None:
    """Run the dealer: draw until hard 17 or soft 18+, then resolve all hands."""
    from backend.models import GameSession, Hand  # noqa: PLC0415

    result = await db.execute(select(GameSession).where(GameSession.id == session_id))
    game_session = result.scalar_one_or_none()
    if not game_session:
        return

    dealer_cards = list(game_session.dealer_cards)
    deck = list(game_session.deck_state)

    # Dealer draws: hits on soft 16 or lower, and on soft 17 (dealer hits soft 17 rule)
    # Stands on hard 17+ or soft 18+
    while True:
        val = eng.hand_value(dealer_cards)
        soft = eng.is_soft(dealer_cards)
        # Stand on hard 17+ or soft 18+
        if val > 17:
            break
        if val == 17 and not soft:
            break
        # Must draw
        if not deck:
            # Reshuffle a new deck if empty (edge case)
            deck = eng.create_deck()
        card, deck = eng.deal_card(deck)
        dealer_cards.append(card)

    game_session.dealer_cards = dealer_cards
    game_session.deck_state = deck
    game_session.status = "finished"

    # Resolve all hands and credit payouts back to users
    result = await db.execute(select(Hand).where(Hand.session_id == session_id))
    hands = result.scalars().all()
    for hand in hands:
        if hand.status in ("active", "standing", "blackjack"):
            outcome, payout = resolve_hand(
                {"cards": hand.cards, "bet": hand.bet, "status": hand.status},
                dealer_cards,
            )
            hand.outcome = outcome
            hand.payout = payout
            hand.status = "finished"

            # Credit payout back to the user's chip balance
            if payout > 0:
                from backend.models import User  # noqa: PLC0415
                result_u = await db.execute(select(User).where(User.id == hand.user_id))
                hand_user = result_u.scalar_one_or_none()
                if hand_user is not None:
                    hand_user.chip_balance += payout

    await db.flush()
