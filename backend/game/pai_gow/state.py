"""backend.game.pai_gow.state — async DB helpers for the PG state machine.

This is the load-bearing async layer between the routers and the pure-logic
modules (cards, evaluator, resolver, fortune, house_way, optimal_set).
Implements the round-6 spec §9.2 (deal), §9.3 (set), §9.4 (timeout
auto-set), §9.5 (resolve), §9.6 (leave-with-refund).

Round-6 concurrency fixes baked in from the start:

  Fix A — deck integrity via row lock (§9.2 step 7):
    Before mutating `pai_gow_rounds.deck_state` or `dealer_dealt_cards`,
    deal_to_player issues `SELECT … FOR UPDATE` on the round row. Two
    concurrent deals on the same round serialize at the DB lock, so no
    "same card dealt to two players" or "cards silently vanishing" race
    can happen.

  Fix B — round-creation race retry (§9.2 step 4):
    The first deal at an empty-round table races to INSERT a new round.
    `UNIQUE(table_id, round_number)` makes only one INSERT succeed; the
    loser catches `IntegrityError` and re-runs the SELECT to join the
    just-created round. Retry exactly once — second-race surfacing as 500
    is acceptable; not retrying at all means a 2-seat simultaneous-deal
    table crashes one player visibly.

All money writes go through escrow at deal time (§9.2 step 6) and refund-
or-payout at resolve (§9.5 step 3-4). The `ante_payout_cents` from
resolver and `fortune_payout_cents` from fortune both follow the
"escrow + payout" pattern documented in §9.5 step 4 ("X to 1" odds): the
escrow refund and the winnings are separate chip_balance additions.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.game.pai_gow import (
    cards as _cards_mod,
    evaluator as _evaluator,
    fortune as _fortune,
    house_way as _house_way,
    optimal_set as _optimal_set,
    resolver as _resolver,
)
from backend.models import (
    FORTUNE_POOL_SINGLETON_ID,
    FortunePool,
    FortunePoolEvent,
    PaiGowPlayerAction,
    PaiGowPlayerHand,
    PaiGowRound,
    PaiGowSeat,
    PaiGowStrategyStreak,
    PaiGowTable,
    User,
)

logger = logging.getLogger(__name__)


# ─── Constants ───────────────────────────────────────────────────────────────

# Round-level timeout: if a round stays in 'playing' status longer than this
# after `playing_started_at`, the lazy auto-set on poll fires (§9.4).
ROUND_PLAYING_TIMEOUT_SECONDS: int = 60

# Cards dealt to the dealer + each player.
DEALER_HAND_SIZE: int = 7
PLAYER_HAND_SIZE: int = 7

# Maximum retry attempts on the round-creation race (round-6 fix B).
ROUND_CREATE_MAX_RETRIES: int = 1


# `HTTPException` is raised directly from state-machine code. FastAPI catches
# it anywhere in the request lifecycle and maps it to the appropriate response.
# Matches the pattern used by blackjack's `routers/game.py`.


# ─── Deal flow (§9.2) ───────────────────────────────────────────────────────


async def deal_to_player(
    db: AsyncSession,
    table_id: uuid.UUID,
    user_id: uuid.UUID,
    bet_cents: int,
    fortune_bet_cents: int,
) -> PaiGowPlayerHand:
    """Per-player deal entry point. Implements §9.2 verbatim.

    Idempotent on `(round_id, user_id)`: if the caller already has a hand
    in the active round, returns it without escrowing or re-dealing.

    Raises HTTPException on validation failures (auto-handled by FastAPI):
      400 — bet out of range, fortune_bet out of range, insufficient chips
      403 — caller not seated at this table
      404 — table not found
    """
    # Step 1: Verify caller is seated at this table.
    table = await _get_table_or_404(db, table_id)
    await _get_seat_or_403(db, table_id, user_id)

    # Step 5 (run early for idempotency): if an active round already exists AND
    # the caller already has a hand on it, return that hand without re-validating.
    # This makes client double-fire / network-retry truly idempotent — even when
    # the UI's bet field changed between the two requests.
    active_round_for_idempotent = await _select_active_round(db, table_id)
    if active_round_for_idempotent is not None:
        existing_hand = await _find_existing_hand(
            db, active_round_for_idempotent.id, user_id
        )
        if existing_hand is not None:
            return existing_hand

    # Step 2 + 3: Validate bet ranges against the table config + chip balance.
    # (Only after the idempotent escape hatch fails.)
    user = await _get_user_or_404(db, user_id)
    _validate_bet_ranges(table, bet_cents, fortune_bet_cents)
    _validate_sufficient_chips(user, bet_cents, fortune_bet_cents)

    # Step 4: Find or create the active round (with IntegrityError retry — fix B).
    rnd = await _find_or_create_active_round(db, table_id)

    # Re-check idempotent in case a concurrent first-deal landed between our
    # SELECT and the validation just above. Cheap belt-and-suspenders.
    existing_hand = await _find_existing_hand(db, rnd.id, user_id)
    if existing_hand is not None:
        return existing_hand

    # Step 6: Escrow chips. Hard floor at 0; the prior _validate_sufficient_chips
    # check ensures this won't underflow.
    user.chip_balance -= (bet_cents + fortune_bet_cents)

    # Steps 7-10: Lock the round row (FOR UPDATE — fix A) and mutate deck_state +
    # dealer_dealt_cards atomically.
    await _lock_round_for_update(db, rnd.id)
    # Re-load the round after the lock so we see any concurrent updates.
    await db.refresh(rnd)

    deck = list(rnd.deck_state)
    dealer_cards = list(rnd.dealer_dealt_cards)

    # Deal dealer cards on the first deal of the round.
    if not dealer_cards:
        dealer_cards, deck = _cards_mod.deal_cards(deck, DEALER_HAND_SIZE)

    # Deal this player's cards.
    player_cards, deck = _cards_mod.deal_cards(deck, PLAYER_HAND_SIZE)

    rnd.dealer_dealt_cards = dealer_cards
    rnd.deck_state = deck

    # Step 11: Insert the player's hand row.
    hand = PaiGowPlayerHand(
        id=uuid.uuid4(),
        round_id=rnd.id,
        user_id=user_id,
        dealt_cards=player_cards,
        bet_cents=bet_cents,
        fortune_bet_cents=fortune_bet_cents,
        action_status="dealt",
        created_at=datetime.now(timezone.utc),
    )
    db.add(hand)
    await db.flush()
    await db.refresh(hand)

    # Step 12: CAS round status `betting → playing`. Empty RETURNING is fine —
    # means another deal already transitioned (second+ player on this round).
    await _cas_round_betting_to_playing(db, rnd.id)

    # Step 13: Contribute to Fortune pool if fortune_bet > 0.
    if fortune_bet_cents > 0:
        await _contribute_to_fortune_pool(db, hand.id)

    await db.flush()
    return hand


async def _find_or_create_active_round(
    db: AsyncSession,
    table_id: uuid.UUID,
) -> PaiGowRound:
    """§9.2 step 4 — find or create the active round on this table.

    Race-safe (round-6 fix B): two simultaneous first-deals racing to create
    the round will have ONE win the `UNIQUE(table_id, round_number)` INSERT;
    the other catches `IntegrityError`, re-runs the SELECT, and joins the
    just-created round. Retried `ROUND_CREATE_MAX_RETRIES` times (default 1).
    """
    for _attempt in range(ROUND_CREATE_MAX_RETRIES + 1):
        # 4a: SELECT for an existing active round.
        rnd = await _select_active_round(db, table_id)
        if rnd is not None:
            return rnd

        # 4b: No active round — try to INSERT a new one inside a SAVEPOINT so
        # an IntegrityError rolls back only the speculative INSERT, NOT the
        # outer transaction. Without the savepoint, asyncpg leaves the outer
        # txn in "aborted" state after IntegrityError and the retry's SELECT
        # fails with "current transaction is aborted, commands ignored until
        # end of transaction block". SQLite is more permissive — it lets you
        # continue after IntegrityError — which is why this bug only surfaces
        # under Postgres / the round-6 fix B regression specifically.
        next_number = await _next_round_number(db, table_id)
        new_round = PaiGowRound(
            id=uuid.uuid4(),
            table_id=table_id,
            round_number=next_number,
            dealer_dealt_cards=[],
            deck_state=_cards_mod.shuffle_deck(_cards_mod.create_deck()),
            status="betting",
            created_at=datetime.now(timezone.utc),
        )
        try:
            async with db.begin_nested():
                db.add(new_round)
                await db.flush()
        except IntegrityError:
            # 4c: Lost the race — UNIQUE(table_id, round_number) hit. The
            # savepoint's __aexit__ already rolled back the speculative INSERT
            # and the outer transaction is still alive. Re-run the SELECT.
            logger.info(
                "round-creation race at table %s round_number=%d, retrying",
                table_id, next_number,
            )
            continue
        await db.refresh(new_round)
        return new_round

    # Exhausted retries — surface as 500 via the caller.
    raise HTTPException(status_code=500, detail="Failed to find or create active round after retries")


async def _select_active_round(
    db: AsyncSession,
    table_id: uuid.UUID,
) -> Optional[PaiGowRound]:
    """§9.2 step 4a — SELECT the highest-numbered active round on this table.

    "Active" means a round still accepting deals or in mid-play, i.e. status
    in (`betting`, `playing`). Used by the deal-flow to decide whether to
    attach to an open round or create round N+1. Display callers want a
    broader view — use `_select_most_recent_round` instead.
    """
    result = await db.execute(
        select(PaiGowRound)
        .where(PaiGowRound.table_id == table_id)
        .where(PaiGowRound.status.in_(("betting", "playing")))
        .order_by(PaiGowRound.round_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _select_most_recent_round(
    db: AsyncSession,
    table_id: uuid.UUID,
) -> Optional[PaiGowRound]:
    """Return the highest-numbered round regardless of status.

    Used by the polling state endpoint so the just-finished round (with
    dealer reveal + win/loss + payout) stays visible to seated players until
    someone deals round N+1. The next `deal` creates a higher-numbered round
    that naturally supersedes the finished one via `ORDER BY round_number
    DESC LIMIT 1`, swapping the result UI back to the fresh betting screen.
    """
    result = await db.execute(
        select(PaiGowRound)
        .where(PaiGowRound.table_id == table_id)
        .order_by(PaiGowRound.round_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _next_round_number(db: AsyncSession, table_id: uuid.UUID) -> int:
    """Next monotonically increasing round_number for this table."""
    result = await db.execute(
        select(func.coalesce(func.max(PaiGowRound.round_number), 0))
        .where(PaiGowRound.table_id == table_id)
    )
    return int(result.scalar_one()) + 1


async def _lock_round_for_update(db: AsyncSession, round_id: uuid.UUID) -> None:
    """§9.2 step 7 — `SELECT … FOR UPDATE` on the round row.

    Round-6 fix A: serializes concurrent deals on the same round at the DB
    layer. Same locking discipline as fortune_pool's row lock in §11.4.

    SQLite (in-memory tests) silently ignores `FOR UPDATE` but still
    serializes writes via its single-writer model, so the deal flow behaves
    identically under tests and Postgres.
    """
    await db.execute(
        select(PaiGowRound.id)
        .where(PaiGowRound.id == round_id)
        .with_for_update()
    )


async def _cas_round_betting_to_playing(
    db: AsyncSession,
    round_id: uuid.UUID,
) -> bool:
    """§9.2 step 12 — compare-and-set round status `betting → playing`.

    Returns True if the CAS succeeded (this deal triggered the transition),
    False if another concurrent deal already transitioned. Either way is
    fine — empty RETURNING is NOT an error.
    """
    stmt = (
        update(PaiGowRound)
        .where(PaiGowRound.id == round_id)
        .where(PaiGowRound.status == "betting")
        .values(status="playing", playing_started_at=datetime.now(timezone.utc))
    )
    result = await db.execute(stmt)
    return (result.rowcount or 0) > 0


# ─── Set flow (§9.3) ────────────────────────────────────────────────────────


async def submit_player_set(
    db: AsyncSession,
    hand_id: uuid.UUID,
    user_id: uuid.UUID,
    front: list,
    back: list,
) -> PaiGowPlayerHand:
    """Per-player set submission. Implements §9.3 verbatim.

    Raises HTTPException:
      400 — invalid split sizes, foul (front strictly > back), invalid cards
      403 — caller doesn't own this hand
      404 — hand not found
      409 — already set/auto-set by another request or timeout
    """
    # 1. Load hand + verify ownership.
    hand = await _get_hand_or_404(db, hand_id)
    if hand.user_id != user_id:
        raise HTTPException(status_code=403, detail="You don't own this hand")

    # 2. Verify split sizes + card membership.
    _validate_split_sizes(front, back)
    _validate_split_card_membership(front, back, list(hand.dealt_cards))

    # 3. Verify foul rule — front STRICTLY > back → reject (round-4 spec §7.4).
    if _is_fouled(front, back):
        raise HTTPException(status_code=400, detail="Foul: front rank exceeds back rank")

    # 4. CAS hand action_status `dealt → set`. Empty rowcount = already set
    # by another request (double-fire) or auto-set by timeout — return 409.
    stmt = (
        update(PaiGowPlayerHand)
        .where(PaiGowPlayerHand.id == hand_id)
        .where(PaiGowPlayerHand.action_status == "dealt")
        .values(
            action_status="set",
            front_cards=front,
            back_cards=back,
        )
    )
    result = await db.execute(stmt)
    if (result.rowcount or 0) == 0:
        raise HTTPException(status_code=409, detail="Hand already set or timed out")
    await db.refresh(hand)

    # 5. Insert player_action row with optimal split + was_optimal.
    await _record_player_action(db, hand, action_type="set",
                                player_front=front, player_back=back)

    # 6. Eager round-state check: if every hand on this round is non-dealt,
    # CAS `playing → dealer_turn` and run resolution inline.
    await _maybe_resolve_round(db, hand.round_id)

    await db.refresh(hand)
    return hand


def _is_fouled(front: list, back: list) -> bool:
    """§7.4 — foul if front strictly > back under §7.3 unified ordering.

    Equality is LEGAL (round-4 spec correction — the high-quad split case
    is the canonical example where back >= front via kicker tiebreak).
    """
    return _evaluator.score_hand(front) > _evaluator.score_hand(back)


async def _record_player_action(
    db: AsyncSession,
    hand: PaiGowPlayerHand,
    *,
    action_type: str,
    player_front: Optional[list],
    player_back: Optional[list],
) -> None:
    """Insert a `pai_gow_player_actions` row recording this set / auto-set.

    Computes `was_optimal` via `optimal_set.evaluate_split` so the streak
    update uses the Chipy oracle (NOT a direct house-way comparison —
    round-7 catch). For auto-set, player_front/back are None; we record
    house_way's output as both player and optimal for replay clarity, and
    was_optimal is True by construction (since auto-set = house way).
    """
    dealt = list(hand.dealt_cards)
    optimal = _optimal_set.find_optimal(dealt)

    if action_type == "auto_set":
        # Auto-set IS house way; record house way for both player and optimal.
        recorded_player_front = list(optimal.front)
        recorded_player_back = list(optimal.back)
        was_optimal = True
    else:
        recorded_player_front = player_front
        recorded_player_back = player_back
        evaluation = _optimal_set.evaluate_split(dealt, player_front, player_back)
        was_optimal = evaluation.is_optimal

    action = PaiGowPlayerAction(
        id=uuid.uuid4(),
        hand_id=hand.id,
        user_id=hand.user_id,
        action_type=action_type,
        player_front=recorded_player_front,
        player_back=recorded_player_back,
        optimal_front=list(optimal.front),
        optimal_back=list(optimal.back),
        was_optimal=was_optimal,
        chipy_explanation=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(action)

    # Update streak ONLY on player-driven sets, per spec §12.6.
    if action_type == "set":
        await _update_streak(db, hand.user_id, was_optimal)


async def _update_streak(db: AsyncSession, user_id: uuid.UUID, was_optimal: bool) -> None:
    """Update `pai_gow_strategy_streaks` for this user on a player-driven set.

    Optimal → current_streak += 1, longest_streak = max(...), total_optimal += 1.
    Suboptimal → current_streak = 0.
    Both → total_played += 1, last_played_at = now.

    Creates the streak row on first play if it doesn't exist (per-user
    singleton, PK on user_id).
    """
    result = await db.execute(
        select(PaiGowStrategyStreak).where(PaiGowStrategyStreak.user_id == user_id)
    )
    streak = result.scalar_one_or_none()
    if streak is None:
        # Explicit zeros — SQLAlchemy column defaults aren't applied to the
        # in-Python instance until INSERT runs, and we mutate before that.
        streak = PaiGowStrategyStreak(
            user_id=user_id,
            current_streak=0,
            longest_streak=0,
            total_optimal=0,
            total_played=0,
        )
        db.add(streak)
        await db.flush()

    if was_optimal:
        streak.current_streak += 1
        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
        streak.total_optimal += 1
    else:
        streak.current_streak = 0

    streak.total_played += 1
    streak.last_played_at = datetime.now(timezone.utc)


# ─── Resolve flow (§9.5) ─────────────────────────────────────────────────────


async def _maybe_resolve_round(db: AsyncSession, round_id: uuid.UUID) -> bool:
    """§9.3 step 6 (eager) + §9.4 (lazy) — if every hand on this round is
    non-dealt, CAS round status `playing → dealer_turn` and run resolution.

    Returns True iff resolution ran.
    """
    # Are all hands non-dealt?
    result = await db.execute(
        select(func.count())
        .select_from(PaiGowPlayerHand)
        .where(PaiGowPlayerHand.round_id == round_id)
        .where(PaiGowPlayerHand.action_status == "dealt")
    )
    dealt_count = int(result.scalar_one())
    if dealt_count > 0:
        return False

    # CAS playing → dealer_turn. Empty rowcount = another path already triggered.
    stmt = (
        update(PaiGowRound)
        .where(PaiGowRound.id == round_id)
        .where(PaiGowRound.status == "playing")
        .values(status="dealer_turn")
    )
    result = await db.execute(stmt)
    if (result.rowcount or 0) == 0:
        return False

    await resolve_round(db, round_id)
    return True


async def resolve_round(db: AsyncSession, round_id: uuid.UUID) -> None:
    """§9.5 — resolution transaction.

    Single DB transaction wraps:
      1. Compute dealer's split via house_way; store as dealer_front/back.
      2. For each hand: foul → LOSE; else compare via resolver.
      3. Apply ante payouts (escrow refund + winnings on WIN; refund on PUSH).
      4. For each hand with fortune_bet > 0: classify Fortune, apply payout
         (escrow refund + winnings on win), update fortune_pool + ledger.
      5. Mark each hand resolved; CAS round dealer_turn → finished.
    """
    rnd = await _get_round_or_404(db, round_id)
    if rnd.status != "dealer_turn":
        # Defensive — caller should have just CAS'd into dealer_turn.
        return

    # 1. Dealer house way.
    dealer_dealt = list(rnd.dealer_dealt_cards)
    dealer_front, dealer_back = _house_way.foxwoods(dealer_dealt)
    rnd.dealer_front = dealer_front
    rnd.dealer_back = dealer_back

    # Score the dealer once for all hands.
    dealer_front_score = _evaluator.score_hand(dealer_front)
    dealer_back_score = _evaluator.score_hand(dealer_back)

    # 2-4. Loop over each player hand and apply payouts.
    result = await db.execute(
        select(PaiGowPlayerHand).where(PaiGowPlayerHand.round_id == round_id)
    )
    hands = result.scalars().all()

    for hand in hands:
        if hand.action_status not in ("set", "auto_set"):
            # Shouldn't happen — caller's CAS guarantees no `dealt` left.
            logger.warning(
                "resolve_round: skipping hand %s with action_status=%s",
                hand.id, hand.action_status,
            )
            continue

        # Ante resolution.
        await _resolve_ante(db, hand, dealer_front_score, dealer_back_score)

        # Fortune resolution (if fortune_bet > 0).
        if hand.fortune_bet_cents > 0:
            await _resolve_fortune(db, hand)

        hand.action_status = "resolved"
        hand.resolved_at = datetime.now(timezone.utc)

    # 5. CAS dealer_turn → finished.
    stmt = (
        update(PaiGowRound)
        .where(PaiGowRound.id == round_id)
        .where(PaiGowRound.status == "dealer_turn")
        .values(status="finished", resolved_at=datetime.now(timezone.utc))
    )
    await db.execute(stmt)
    await db.flush()


async def _resolve_ante(
    db: AsyncSession,
    hand: PaiGowPlayerHand,
    dealer_front_score: tuple,
    dealer_back_score: tuple,
) -> None:
    """§9.5 step 3 — apply ante payout to chip_balance.

    Escrow accounting (the bet was deducted at deal time):
      WIN  → chip_balance += 2 * bet_cents  (escrow refund + winnings)
      PUSH → chip_balance += bet_cents       (escrow refund)
      LOSE → chip_balance += 0               (escrow stays with house)

    `ante_payout_cents` on the hand records the NET delta over the cycle
    (matches resolver.ante_payout_cents): WIN=+bet, PUSH=0, LOSE=-bet.
    """
    # Foul short-circuit (defensive — set flow rejects fouls; this only
    # protects against fixture-induced fouled-but-set states).
    if _is_fouled(list(hand.front_cards or []), list(hand.back_cards or [])):
        hand.front_compare = None
        hand.back_compare = None
        hand.hand_result = "lose"
        hand.ante_payout_cents = -hand.bet_cents
        return

    player_front_score = _evaluator.score_hand(list(hand.front_cards))
    player_back_score = _evaluator.score_hand(list(hand.back_cards))

    front_cmp = _resolver.compare_side(player_front_score, dealer_front_score)
    back_cmp = _resolver.compare_side(player_back_score, dealer_back_score)
    result = _resolver.resolve_hand(front_cmp, back_cmp)

    hand.front_compare = front_cmp.value
    hand.back_compare = back_cmp.value
    hand.hand_result = result.value
    hand.ante_payout_cents = _resolver.ante_payout_cents(result, hand.bet_cents)

    # Apply chip_balance delta (escrow-aware).
    user = (await db.execute(select(User).where(User.id == hand.user_id))).scalar_one()
    if result is _resolver.HandResult.WIN:
        user.chip_balance += 2 * hand.bet_cents
    elif result is _resolver.HandResult.PUSH:
        user.chip_balance += hand.bet_cents
    # LOSE: no chip_balance change (escrow stays with house).


async def _resolve_fortune(db: AsyncSession, hand: PaiGowPlayerHand) -> None:
    """§9.5 step 4 + §11.4 — apply Fortune side-bet payout.

    Per the spec memo committed earlier: payout pathway is
    `chip_balance += fortune_bet_cents + fortune_payout_cents` for both
    fixed and pool tiers — the bet refund and the winnings are separate
    additions, matching the ante's "WIN = 2*bet" structure. Non-qualifying
    hands forfeit the fortune_bet (escrow stays with the house).
    """
    dealt = list(hand.dealt_cards)
    qualification = _fortune.classify_fortune(dealt, hand.fortune_bet_cents)
    if qualification is None:
        # Non-qualifying — fortune_bet stays with the house.
        hand.fortune_payout_cents = None
        return

    if qualification.is_fixed_tier:
        payout = _fortune.fixed_payout_cents(qualification.category, hand.fortune_bet_cents)
        await _write_fortune_event(
            db, hand_id=hand.id,
            event_type="fixed_payout",
            payout_cents=payout,
        )
    else:
        # Pool tier (GRAND or MAJOR) — row-lock fortune_pool.
        payout = await _drain_pool_with_lock(db, hand_id=hand.id, tier=qualification.tier)

    hand.fortune_payout_cents = payout

    # Escrow refund + winnings (matches spec §9.5 step 4 memo).
    user = (await db.execute(select(User).where(User.id == hand.user_id))).scalar_one()
    user.chip_balance += hand.fortune_bet_cents + payout


async def _drain_pool_with_lock(
    db: AsyncSession,
    hand_id: uuid.UUID,
    tier: _fortune.FortuneTier,
) -> int:
    """§11.4 — `SELECT … FOR UPDATE` on fortune_pool, compute, UPDATE, ledger.

    Returns the payout cents. Concurrent winners serialize on the row lock;
    second-arrival winners observe `amount = seed` and collect 0.
    """
    # FOR UPDATE row lock on the singleton.
    result = await db.execute(
        select(FortunePool)
        .where(FortunePool.id == FORTUNE_POOL_SINGLETON_ID)
        .with_for_update()
    )
    pool = result.scalar_one()

    payout, new_amount = _fortune.pool_payout_cents(
        tier, pool.amount_cents, pool.seed_cents
    )

    pool.amount_cents = new_amount
    pool.last_updated_at = datetime.now(timezone.utc)

    event_type = "grand_payout" if tier is _fortune.FortuneTier.GRAND else "major_payout"
    await _write_fortune_event(
        db, hand_id=hand_id,
        event_type=event_type,
        payout_cents=payout,
        post_balance_override=new_amount,
    )
    return payout


async def _contribute_to_fortune_pool(db: AsyncSession, hand_id: uuid.UUID) -> None:
    """§11.3 — atomic single-statement UPDATE adding the fixed contribution.

    Caller invokes this only when the hand has fortune_bet > 0.
    """
    stmt = (
        update(FortunePool)
        .where(FortunePool.id == FORTUNE_POOL_SINGLETON_ID)
        .values(
            amount_cents=FortunePool.amount_cents + _fortune.CONTRIBUTION_PER_DEAL_CENTS,
            last_updated_at=datetime.now(timezone.utc),
        )
    )
    await db.execute(stmt)

    # Read the post-balance to write the ledger entry.
    result = await db.execute(
        select(FortunePool.amount_cents)
        .where(FortunePool.id == FORTUNE_POOL_SINGLETON_ID)
    )
    post_balance = int(result.scalar_one())

    db.add(FortunePoolEvent(
        id=uuid.uuid4(),
        hand_id=hand_id,
        event_type="contribute",
        contribution_cents=_fortune.CONTRIBUTION_PER_DEAL_CENTS,
        payout_cents=0,
        post_balance_cents=post_balance,
        created_at=datetime.now(timezone.utc),
    ))


async def _write_fortune_event(
    db: AsyncSession,
    *,
    hand_id: uuid.UUID,
    event_type: str,
    payout_cents: int,
    post_balance_override: Optional[int] = None,
) -> None:
    """Append a row to fortune_pool_events for the audit ledger (§11.5/§11.6)."""
    if post_balance_override is not None:
        post_balance = post_balance_override
    else:
        # Fixed-tier payouts don't touch the pool — record the current balance.
        result = await db.execute(
            select(FortunePool.amount_cents)
            .where(FortunePool.id == FORTUNE_POOL_SINGLETON_ID)
        )
        post_balance = int(result.scalar_one())

    db.add(FortunePoolEvent(
        id=uuid.uuid4(),
        hand_id=hand_id,
        event_type=event_type,
        contribution_cents=0,
        payout_cents=payout_cents,
        post_balance_cents=post_balance,
        created_at=datetime.now(timezone.utc),
    ))


# ─── Timeout auto-set (§9.4) ────────────────────────────────────────────────


async def auto_set_round_if_timed_out(db: AsyncSession, round_id: uuid.UUID) -> bool:
    """§9.4 — lazy timeout check called from the state polling endpoint.

    If the round has been in 'playing' status for > ROUND_PLAYING_TIMEOUT_SECONDS
    past playing_started_at, auto-set every still-`dealt` hand via house way
    and trigger resolution. Returns True if any auto-set fired.
    """
    rnd = await _get_round_or_404(db, round_id)
    if rnd.status != "playing" or rnd.playing_started_at is None:
        return False

    # Defensive: `DateTime(timezone=True)` round-trips as aware on Postgres
    # but the SQLite test backend can return naive — normalize to UTC so the
    # subtraction below doesn't TypeError. Stored values are always UTC.
    started = rnd.playing_started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - started).total_seconds()
    if age <= ROUND_PLAYING_TIMEOUT_SECONDS:
        return False

    # Auto-set each `dealt` hand using house way.
    result = await db.execute(
        select(PaiGowPlayerHand)
        .where(PaiGowPlayerHand.round_id == round_id)
        .where(PaiGowPlayerHand.action_status == "dealt")
    )
    any_fired = False
    for hand in result.scalars().all():
        dealt_cards = list(hand.dealt_cards)
        hw_front, hw_back = _house_way.foxwoods(dealt_cards)
        # CAS dealt → auto_set
        cas = (
            update(PaiGowPlayerHand)
            .where(PaiGowPlayerHand.id == hand.id)
            .where(PaiGowPlayerHand.action_status == "dealt")
            .values(
                action_status="auto_set",
                front_cards=hw_front,
                back_cards=hw_back,
            )
        )
        cas_result = await db.execute(cas)
        if (cas_result.rowcount or 0) > 0:
            await db.refresh(hand)
            await _record_player_action(
                db, hand, action_type="auto_set",
                player_front=None, player_back=None,
            )
            any_fired = True

    if any_fired:
        await _maybe_resolve_round(db, round_id)

    return any_fired


# ─── Leave flow (§9.6) ──────────────────────────────────────────────────────


async def leave_table_with_refund(
    db: AsyncSession,
    table_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """§9.6 — leave handler with escrow refund.

    Behavior by round status:
      no active round / 'finished' — just remove the seat.
      'betting' or 'playing'        — refund escrow, delete player_hand,
                                      delete round if no other hands remain.
      'dealer_turn'                  — remove seat only (resolution handles
                                      payouts in its own transaction).
    """
    # Remove the seat (always).
    seat_result = await db.execute(
        select(PaiGowSeat)
        .where(PaiGowSeat.table_id == table_id)
        .where(PaiGowSeat.user_id == user_id)
    )
    seat = seat_result.scalar_one_or_none()
    if seat is not None:
        await db.delete(seat)
        await db.flush()

    # Look for an active round to handle escrow.
    rnd = await _select_active_round(db, table_id)
    if rnd is None or rnd.status in ("dealer_turn", "finished"):
        return

    hand_result = await db.execute(
        select(PaiGowPlayerHand)
        .where(PaiGowPlayerHand.round_id == rnd.id)
        .where(PaiGowPlayerHand.user_id == user_id)
    )
    hand = hand_result.scalar_one_or_none()
    if hand is None:
        return

    # Refund escrow.
    user = await _get_user_or_404(db, user_id)
    user.chip_balance += hand.bet_cents + hand.fortune_bet_cents

    # Delete the player_hand (cascades to player_actions).
    await db.delete(hand)
    await db.flush()

    # If no other hands remain on this round, delete the round.
    remaining = await db.execute(
        select(func.count())
        .select_from(PaiGowPlayerHand)
        .where(PaiGowPlayerHand.round_id == rnd.id)
    )
    if int(remaining.scalar_one()) == 0:
        await db.delete(rnd)
        await db.flush()


# ─── Read helpers used by routers ────────────────────────────────────────────


async def get_active_round_state(
    db: AsyncSession,
    table_id: uuid.UUID,
    viewer_user_id: Optional[uuid.UUID] = None,
) -> Optional[PaiGowRound]:
    """Return the round to display on the polling `/state` endpoint.

    Includes finished rounds so the player sees the dealer reveal + win/loss
    + payout after resolve, until a new `deal` opens round N+1 (which then
    supersedes the finished one via higher round_number). Triggers a lazy
    timeout check (§9.4) only for rounds that are actually mid-flow —
    finished rounds need no timeout handling. Callers handle card-visibility
    masking based on `round.status` per spec §13.
    """
    rnd = await _select_most_recent_round(db, table_id)
    if rnd is None:
        return None
    if rnd.status in ("betting", "playing"):
        await auto_set_round_if_timed_out(db, rnd.id)
        await db.refresh(rnd)
    return rnd


# ─── Internal validation helpers ────────────────────────────────────────────


async def _get_table_or_404(db: AsyncSession, table_id: uuid.UUID) -> PaiGowTable:
    result = await db.execute(select(PaiGowTable).where(PaiGowTable.id == table_id))
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=404, detail="Pai Gow table not found")
    return table


async def _get_seat_or_403(
    db: AsyncSession,
    table_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PaiGowSeat:
    result = await db.execute(
        select(PaiGowSeat)
        .where(PaiGowSeat.table_id == table_id)
        .where(PaiGowSeat.user_id == user_id)
    )
    seat = result.scalar_one_or_none()
    if seat is None:
        raise HTTPException(status_code=403, detail="You are not seated at this Pai Gow table")
    return seat


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _get_hand_or_404(db: AsyncSession, hand_id: uuid.UUID) -> PaiGowPlayerHand:
    result = await db.execute(
        select(PaiGowPlayerHand).where(PaiGowPlayerHand.id == hand_id)
    )
    hand = result.scalar_one_or_none()
    if hand is None:
        raise HTTPException(status_code=404, detail="Pai Gow hand not found")
    return hand


async def _get_round_or_404(db: AsyncSession, round_id: uuid.UUID) -> PaiGowRound:
    result = await db.execute(
        select(PaiGowRound).where(PaiGowRound.id == round_id)
    )
    rnd = result.scalar_one_or_none()
    if rnd is None:
        raise HTTPException(status_code=404, detail="Pai Gow round not found")
    return rnd


async def _find_existing_hand(
    db: AsyncSession,
    round_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[PaiGowPlayerHand]:
    result = await db.execute(
        select(PaiGowPlayerHand)
        .where(PaiGowPlayerHand.round_id == round_id)
        .where(PaiGowPlayerHand.user_id == user_id)
    )
    return result.scalar_one_or_none()


def _validate_bet_ranges(
    table: PaiGowTable,
    bet_cents: int,
    fortune_bet_cents: int,
) -> None:
    if bet_cents < table.min_bet_cents:
        raise HTTPException(status_code=400, detail=
            f"Bet {bet_cents} below table minimum {table.min_bet_cents}"
        )
    if bet_cents > table.max_bet_cents:
        raise HTTPException(status_code=400, detail=
            f"Bet {bet_cents} above table maximum {table.max_bet_cents}"
        )
    if fortune_bet_cents < 0:
        raise HTTPException(status_code=400, detail="Fortune bet cannot be negative")
    if fortune_bet_cents > 0:
        if fortune_bet_cents < table.min_fortune_bet_cents:
            raise HTTPException(status_code=400, detail=
                f"Fortune bet {fortune_bet_cents} below minimum "
                f"{table.min_fortune_bet_cents}"
            )
        if fortune_bet_cents > table.max_fortune_bet_cents:
            raise HTTPException(status_code=400, detail=
                f"Fortune bet {fortune_bet_cents} above maximum "
                f"{table.max_fortune_bet_cents}"
            )


def _validate_sufficient_chips(
    user: User,
    bet_cents: int,
    fortune_bet_cents: int,
) -> None:
    total = bet_cents + fortune_bet_cents
    if user.chip_balance < total:
        raise HTTPException(status_code=400, detail=
            f"Insufficient chips: need {total}, have {user.chip_balance}"
        )


def _validate_split_sizes(front: list, back: list) -> None:
    if len(front) != 2:
        raise HTTPException(status_code=400, detail=f"Front must be exactly 2 cards, got {len(front)}")
    if len(back) != 5:
        raise HTTPException(status_code=400, detail=f"Back must be exactly 5 cards, got {len(back)}")


def _validate_split_card_membership(
    front: list,
    back: list,
    dealt: list,
) -> None:
    """All cards in front + back must come from the dealt set. No duplicates."""
    submitted_keys = [(c.get("suit"), c.get("value")) for c in (front + back)]
    if len(set(submitted_keys)) != len(submitted_keys):
        raise HTTPException(status_code=400, detail="Duplicate card in submitted split")
    dealt_keys = [(c.get("suit"), c.get("value")) for c in dealt]
    for key in submitted_keys:
        if key not in dealt_keys:
            raise HTTPException(status_code=400, detail=f"Card {key} not in dealt hand")
        # Remove first occurrence so jokers / dup ranks count correctly.
        dealt_keys.remove(key)
