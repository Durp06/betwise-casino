"""
test_payout_no_mint.py — regression test for P1 (no chip minting).

Finding guarded: **P1** — `_finalize_payouts` previously computed the prize pool
as ``buy_in_cents * (1 + bot_count)`` and split it across positions, even though
only the human ever paid a buy-in (poker_tables.py debits just the human; bots
have ``user_id=None``). That minted unbacked chips into the human's balance on a
win — an unbounded inflation bug.

The fix (poker_game.py::_finalize_payouts) collects only the real chips that
entered the table (``prize_pool = tournament.buy_in_cents``) and pays it
winner-take-all to the 1st-place finisher. Net: a win is break-even (refund of
the human's own buy-in), a loss forfeits the buy-in (a sink, not a mint).

Invariant asserted here: **no real user is ever credited more than the real
chips that entered** — concretely, the sum of all real-user credits from a
single tournament is ``<= buy_in_cents``, and the winner is credited *exactly*
``buy_in_cents`` (never a multiple of it).

Style: pytest-asyncio + in-memory SQLite, using the ``db`` fixture and
``seed_user`` from backend/tests/conftest.py. The helper under test is the pure
SQL helper ``_finalize_payouts`` so the test exercises the money path directly
without driving a full hand to completion.
"""

from __future__ import annotations

import uuid

import pytest

from backend.tests.conftest import TEST_USER_ID, seed_user

BUY_IN_CENTS = 10_000
BOT_COUNT = 7
STARTING_STACK = 1_500


async def _seed_tournament_and_seats(
    db,
    *,
    human_user_id: uuid.UUID,
    human_busts: bool,
):
    """Create a PokerTournament (buy_in=10000, bot_count=7) plus its seats.

    Seat 0 is the human; seats 1..7 are bots (user_id=None). When
    ``human_busts`` is False the human survives (1st place) and every bot is
    busted; when True the human busts last and a bot would be 1st (no bot is
    creditable since bots have no user_id).

    Returns ``(tournament, seats)``.
    """
    from backend.models import PokerSeat, PokerTournament  # noqa: PLC0415

    tournament = PokerTournament(
        id=uuid.uuid4(),
        bot_count=BOT_COUNT,
        advice_mode="odds",
        buy_in_cents=BUY_IN_CENTS,
        starting_stack_chips=STARTING_STACK,
        hands_per_level=10,
        seed=12345,
        status="active",
        button_seat=0,
        current_hand_number=5,
    )
    db.add(tournament)
    await db.flush()

    seats: list[PokerSeat] = []
    n_seats = 1 + BOT_COUNT  # human + bots

    # Human seat (seat 0).
    human_seat = PokerSeat(
        id=uuid.uuid4(),
        tournament_id=tournament.id,
        user_id=human_user_id,
        seat_number=0,
        archetype_name=None,
        starting_stack=STARTING_STACK,
        # If the human survives they hold all the chips on the table; if they
        # bust their stack is 0.
        current_stack=0 if human_busts else STARTING_STACK * n_seats,
        is_bust=human_busts,
        # When the human busts they finish 1st-to-bust-out is position 1; here we
        # model them busting LAST (highest bust_position) so the sort still tries
        # to make them "best" among real users — proving even then no over-credit.
        bust_position=1 if human_busts else None,
        is_bot=False,
    )
    db.add(human_seat)
    seats.append(human_seat)

    # Bot seats (1..BOT_COUNT). All busted. bust_position descends so seat 1 is
    # the last bot standing when the human survives.
    for i in range(1, n_seats):
        bot_seat = PokerSeat(
            id=uuid.uuid4(),
            tournament_id=tournament.id,
            user_id=None,
            seat_number=i,
            archetype_name="tag",
            starting_stack=STARTING_STACK,
            current_stack=(STARTING_STACK * n_seats) if human_busts and i == 1 else 0,
            is_bust=not (human_busts and i == 1),
            bust_position=None if (human_busts and i == 1) else (n_seats - i + 1),
            is_bot=True,
        )
        db.add(bot_seat)
        seats.append(bot_seat)

    await db.flush()
    return tournament, seats


@pytest.mark.asyncio
async def test_prize_pool_is_buy_in_not_multiplied(db):
    """P1: prize_pool must equal buy_in_cents, NOT buy_in_cents*(1+bot_count).

    Smallest possible assertion against the computed pool — even if the DB
    wiring below changed, this guards the formula at the root.
    """
    from backend.routers import poker_game  # noqa: PLC0415

    human = await seed_user(db, TEST_USER_ID, "winner", chip_balance=90_000)
    tournament, seats = await _seed_tournament_and_seats(
        db, human_user_id=human.id, human_busts=False
    )

    before = human.chip_balance
    await poker_game._finalize_payouts(tournament, seats, db)
    await db.flush()
    await db.refresh(human)
    credited = human.chip_balance - before

    # The buggy formula would have credited 10000*(1+7)=80000. The fix credits
    # exactly the real stake collected: 10000.
    assert credited == BUY_IN_CENTS, (
        f"winner credited {credited}, expected exactly buy_in_cents={BUY_IN_CENTS} "
        f"(buggy multiplied pool would be {BUY_IN_CENTS * (1 + BOT_COUNT)})"
    )
    # Never a multiple of the buy-in (the mint signature).
    assert credited <= BUY_IN_CENTS
    assert credited % BUY_IN_CENTS == 0 and credited // BUY_IN_CENTS == 1


@pytest.mark.asyncio
async def test_sum_of_real_user_credits_le_buy_in(db):
    """P1 invariant: total credited across ALL real users <= buy_in_cents.

    Bots have user_id=None and are never credited, so the table can never pay
    out more real chips than entered (no mint).
    """
    from backend.models import User  # noqa: PLC0415
    from backend.routers import poker_game  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    human = await seed_user(db, TEST_USER_ID, "soleplayer", chip_balance=90_000)
    tournament, seats = await _seed_tournament_and_seats(
        db, human_user_id=human.id, human_busts=False
    )

    # Snapshot every real user's balance before.
    real_user_ids = [s.user_id for s in seats if s.user_id is not None]
    before_balances: dict[uuid.UUID, int] = {}
    for uid in real_user_ids:
        u = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        before_balances[uid] = u.chip_balance

    await poker_game._finalize_payouts(tournament, seats, db)
    await db.flush()

    total_credited = 0
    for uid in real_user_ids:
        u = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        total_credited += u.chip_balance - before_balances[uid]

    assert total_credited <= BUY_IN_CENTS, (
        f"sum of real-user credits {total_credited} exceeds buy_in_cents "
        f"{BUY_IN_CENTS} — chips were minted"
    )
    # Tournament marked complete by the helper.
    assert tournament.status == "complete"


@pytest.mark.asyncio
async def test_busted_human_is_not_credited(db):
    """P1: a losing human (busted out) must receive nothing — the buy-in is a
    sink. Even though a bot 'wins', bots have no user_id so no real chips are
    minted to anyone."""
    from backend.models import User  # noqa: PLC0415
    from backend.routers import poker_game  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    human = await seed_user(db, TEST_USER_ID, "loser", chip_balance=90_000)
    tournament, seats = await _seed_tournament_and_seats(
        db, human_user_id=human.id, human_busts=True
    )

    before = human.chip_balance
    await poker_game._finalize_payouts(tournament, seats, db)
    await db.flush()

    refreshed = (await db.execute(select(User).where(User.id == human.id))).scalar_one()
    credited = refreshed.chip_balance - before

    # A loss forfeits the buy-in: no credit (and certainly never more than the
    # stake). This is the sink that balances the winner-take-all refund.
    assert credited == 0, f"busted human was credited {credited}; expected 0 (loss is a sink)"
    assert credited <= BUY_IN_CENTS
