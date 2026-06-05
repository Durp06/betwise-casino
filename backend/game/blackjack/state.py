"""
state.py — Game state machine for BetWise Casino blackjack.

Design constraints (specs/betwise-casino.md §T7):
- Async functions that take an AsyncSession.
- resolve_hand is a pure function (no DB) for easy unit testing.
- run_dealer hits until hard 17+ (dealer hits soft 17).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
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

    # Dealer natural blackjack beats any non-natural hand (including a 3-card 21).
    # This branch MUST come before the generic value compare so that a player with
    # a 3-card total of 21 (not a blackjack) correctly loses to a dealer natural.
    if eng.is_blackjack(dealer_cards):
        return ("loss", 0)

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
        # No more active players — trigger dealer turn. Nobody is on the clock now.
        result = await db.execute(select(GameSession).where(GameSession.id == session_id))
        game_session = result.scalar_one_or_none()
        if game_session and game_session.status == "playing":
            game_session.status = "dealer_turn"
            await clear_all_deadlines(session_id, db)
            await db.flush()
            await run_dealer(session_id, db)
    else:
        # A new player is on the clock — give them a fresh 30s move deadline.
        await stamp_current_deadline(session_id, db, force=True)


async def maybe_start_round(table_id: uuid.UUID, db: AsyncSession) -> bool:
    """Deal a waiting betting round once it's ready, flipping it to 'playing'.

    A round is ready when EVERY seated player has placed a bet, OR the betting
    window (BLACKJACK_BETTING_WINDOW_SECONDS past the session's created_at) has
    elapsed with at least one bet down — so a single no-show can't stall the
    table. Lazy + idempotent: safe to call from the place-bet path and the
    /state poll. Returns True iff it dealt the round.

    This is the synchronized-deal half of the multiplayer betting round: bets are
    collected with no cards (status 'active', empty `cards`) while the session is
    'betting'; this deals everyone + the dealer together and starts seat-order play.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.game.timer import BLACKJACK_BETTING_WINDOW_SECONDS  # noqa: PLC0415
    from backend.models import CasinoTable, GameSession, Hand, TableSeat  # noqa: PLC0415

    # Lock the table's open betting session (if any) so two final bets can't
    # both deal. SQLite ignores FOR UPDATE but serializes writes; Postgres locks.
    session = (await db.execute(
        select(GameSession)
        .where((GameSession.table_id == table_id) & (GameSession.status == "betting"))
        .with_for_update()
    )).scalar_one_or_none()
    if session is None:
        return False

    # Bets placed this round = hands in the betting session.
    hands = (await db.execute(
        select(Hand).where(Hand.session_id == session.id)
    )).scalars().all()
    if not hands:
        return False  # session open but nobody has bet yet

    seat_count = int((await db.execute(
        select(func.count(TableSeat.id)).where(TableSeat.table_id == table_id)
    )).scalar_one())

    all_seated_bet = len(hands) >= seat_count
    # created_at may read back tz-naive on SQLite; normalize before comparing.
    started = session.created_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    window_elapsed = (
        datetime.now(timezone.utc) - started
    ).total_seconds() > BLACKJACK_BETTING_WINDOW_SECONDS

    if not (all_seated_bet or window_elapsed):
        return False  # keep waiting for the rest of the table

    # ── Deal the round ───────────────────────────────────────────────────────
    deck = list(session.deck_state)
    dealer_cards = list(session.dealer_cards)
    if not dealer_cards:
        d1, deck = eng.deal_card(deck)
        d2, deck = eng.deal_card(deck)
        dealer_cards = [d1, d2]  # [upcard, hole] — hole masked by _get_table_state

    for hand in hands:
        if not hand.cards:  # only the undealt bets
            c1, deck = eng.deal_card(deck)
            c2, deck = eng.deal_card(deck)
            hand.cards = [c1, c2]
            # status stays "active": a natural is paid by resolve_hand (which
            # checks the cards regardless of status), matching the prior path.

    session.dealer_cards = dealer_cards
    session.deck_state = deck
    session.status = "playing"

    # Parity with the old deal path — reflect play on the table row.
    table = (await db.execute(
        select(CasinoTable).where(CasinoTable.id == table_id)
    )).scalar_one_or_none()
    if table is not None:
        table.status = "playing"

    await db.flush()
    # Put the lowest-seat active hand on the clock (advance_turn stamps it).
    await advance_turn(session.id, db)
    return True


# ─── Move timer (per-player 30s clock) ───────────────────────────────────────
# The current actor is the lowest-seat `active` hand; only it carries a non-null
# move_deadline_at. Enforcement is lazy — see enforce_timeout, called from the
# /action and /state router paths. See backend/game/timer.py for the constant.


async def _current_active_hand(session_id: uuid.UUID, db: AsyncSession):
    """The current actor: the lowest-seat `active` hand, or None. Mirrors
    get_current_player's seat ordering but returns the Hand, not the User."""
    from backend.models import GameSession, Hand, TableSeat  # noqa: PLC0415

    game_session = (await db.execute(
        select(GameSession).where(GameSession.id == session_id)
    )).scalar_one_or_none()
    if not game_session:
        return None
    stmt = (
        select(Hand)
        .outerjoin(
            TableSeat,
            (TableSeat.user_id == Hand.user_id) & (TableSeat.table_id == game_session.table_id),
        )
        .where(Hand.session_id == session_id)
        .where(Hand.status == "active")
        .order_by(TableSeat.seat_number.asc().nullslast())
    )
    return (await db.execute(stmt)).scalars().first()


async def stamp_current_deadline(session_id: uuid.UUID, db: AsyncSession, force: bool = False) -> None:
    """Put the current actor on a 30s clock and clear everyone else's.

    The deadline-iff-actor invariant: `move_deadline_at` is non-null only on the
    lowest-seat active hand. With force=False an existing deadline on the current
    actor is preserved (so a co-player dealing in doesn't restart your clock);
    force=True resets it (the per-decision reset after a hit, or when the turn
    advances to a new actor)."""
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.game.timer import move_deadline  # noqa: PLC0415
    from backend.models import Hand  # noqa: PLC0415

    current = await _current_active_hand(session_id, db)
    hands = (await db.execute(select(Hand).where(Hand.session_id == session_id))).scalars().all()
    now = datetime.now(timezone.utc)
    for h in hands:
        if current is not None and h.id == current.id:
            if force or h.move_deadline_at is None:
                h.move_deadline_at = move_deadline(now)
        elif h.move_deadline_at is not None:
            h.move_deadline_at = None
    await db.flush()


async def clear_all_deadlines(session_id: uuid.UUID, db: AsyncSession) -> None:
    """Clear the move deadline on every hand in a session (nobody on the clock)."""
    from backend.models import Hand  # noqa: PLC0415

    hands = (await db.execute(select(Hand).where(Hand.session_id == session_id))).scalars().all()
    for h in hands:
        h.move_deadline_at = None
    await db.flush()


async def enforce_timeout(table_id: uuid.UUID, db: AsyncSession) -> bool:
    """Lazily auto-STAND the current actor if their move clock has expired.

    Double-checked locking: a cheap unlocked read short-circuits the common
    (not-expired) case; only on an actually-expired deadline do we lock the
    session row, re-validate, and resolve — so two concurrent /state polls can't
    both fire. Auto-stand is the only chip-safe blackjack timeout (an auto-hit
    could bust the player). Returns True if a timeout was enforced."""
    from datetime import datetime, timezone  # noqa: PLC0415

    from backend.game.timer import is_expired  # noqa: PLC0415
    from backend.models import GameSession  # noqa: PLC0415

    session = (await db.execute(
        select(GameSession).where(
            (GameSession.table_id == table_id) & (GameSession.status == "playing")
        )
    )).scalar_one_or_none()
    if session is None:
        return False
    current = await _current_active_hand(session.id, db)
    if current is None or not is_expired(current.move_deadline_at, datetime.now(timezone.utc)):
        return False

    # Expired — lock the session row and re-validate before mutating.
    session = (await db.execute(
        select(GameSession).where(GameSession.id == session.id).with_for_update()
    )).scalar_one_or_none()
    if session is None or session.status != "playing":
        return False
    current = await _current_active_hand(session.id, db)
    if current is None or not is_expired(current.move_deadline_at, datetime.now(timezone.utc)):
        return False  # a concurrent request already resolved it

    current.status = "standing"
    current.move_deadline_at = None
    await db.flush()
    await advance_turn(session.id, db)
    return True


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
