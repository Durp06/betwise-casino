"""
test_blackjack_mp_betting.py — synchronized multiplayer betting round.

Drives the SQL helpers directly with explicit user_ids (the HTTP fixtures share
one global auth override, so they can't act as two distinct users in one test).
Covers specs/blackjack-mp-betting-round.md AC1-AC6.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.routers.game import _deal_hand, _take_action
from backend.routers.tables import _get_table_state, _join_seat
from backend.tests.conftest import OTHER_USER_ID, TEST_USER_ID, seed_table, seed_user


async def _setup_two_seated(db):
    await seed_user(db, TEST_USER_ID, "alice", 100_000)
    await seed_user(db, OTHER_USER_ID, "bob", 100_000)
    table = await seed_table(db, max_seats=3, min_bet=500, max_bet=50_000)
    await _join_seat(table.id, TEST_USER_ID, db)
    await _join_seat(table.id, OTHER_USER_ID, db)
    return table


def _hand_for(state, user_id):
    return next((h for h in state.hands if h.user_id == user_id), None)


async def test_ac1_bet_waits_for_other_seated_player(db):
    """A bets but B hasn't — the round must NOT deal yet."""
    table = await _setup_two_seated(db)

    a_hand = await _deal_hand(table.id, TEST_USER_ID, 1_000, db)
    assert a_hand.cards == []  # bet placed, no cards dealt

    state = await _get_table_state(table.id, TEST_USER_ID, db)
    assert state.session.status == "betting"
    assert state.session.dealer_cards == []  # dealer not dealt during betting
    # A's chips were escrowed.
    a_seat = next(s for s in state.seats if s.user_id == TEST_USER_ID)
    assert a_seat.chip_balance == 99_000


async def test_ac2_all_bet_deals_together_one_actor(db):
    """Once both seated players bet, the round auto-deals: both get cards,
    dealer is dealt (hole masked), and exactly one current actor (seat 1)."""
    table = await _setup_two_seated(db)
    await _deal_hand(table.id, TEST_USER_ID, 1_000, db)
    await _deal_hand(table.id, OTHER_USER_ID, 1_000, db)

    state = await _get_table_state(table.id, TEST_USER_ID, db)
    # Deal happened together — both hands have 2 cards.
    assert len(state.hands) == 2
    assert all(len(h.cards) == 2 for h in state.hands)
    # Dealer dealt; hole card masked while playing.
    assert len(state.session.dealer_cards) == 2
    assert state.session.dealer_cards[1] is None

    if state.session.status == "playing":
        actors = [h for h in state.hands if h.move_deadline_at is not None]
        assert len(actors) == 1  # exactly one player on the clock
        assert actors[0].user_id == TEST_USER_ID  # lowest seat acts first


async def test_ac3_single_player_deals_immediately(db):
    """A lone seated player's bet deals immediately (no one to wait for)."""
    await seed_user(db, TEST_USER_ID, "alice", 100_000)
    table = await seed_table(db, max_seats=3)
    await _join_seat(table.id, TEST_USER_ID, db)

    a_hand = await _deal_hand(table.id, TEST_USER_ID, 1_000, db)
    assert len(a_hand.cards) == 2  # dealt right away

    state = await _get_table_state(table.id, TEST_USER_ID, db)
    assert state.session.status == "playing"


async def test_ac4_betting_window_timeout_deals_bettors(db):
    """If B never bets, the betting window elapsing deals the players who did."""
    from backend.models import GameSession

    table = await _setup_two_seated(db)
    await _deal_hand(table.id, TEST_USER_ID, 1_000, db)  # only A bets

    state = await _get_table_state(table.id, TEST_USER_ID, db)
    assert state.session.status == "betting"  # still waiting on B

    # Backdate the session so the betting window has elapsed.
    sess = (
        await db.execute(select(GameSession).where(GameSession.table_id == table.id))
    ).scalar_one()
    sess.created_at = datetime.now(timezone.utc) - timedelta(seconds=600)
    await db.flush()

    # Next poll triggers the timeout deal (just A).
    state = await _get_table_state(table.id, TEST_USER_ID, db)
    assert state.session.status == "playing"
    assert len(state.hands) == 1
    assert len(state.hands[0].cards) == 2


async def test_ac5_cannot_bet_during_play(db):
    """Betting is closed once the active round is playing — a late bet 409s."""
    from fastapi import HTTPException

    await seed_user(db, TEST_USER_ID, "alice", 100_000)
    await seed_user(db, OTHER_USER_ID, "bob", 100_000)
    table = await seed_table(db, max_seats=3)
    await _join_seat(table.id, TEST_USER_ID, db)
    # A alone bets -> deals immediately -> playing.
    await _deal_hand(table.id, TEST_USER_ID, 1_000, db)
    state = await _get_table_state(table.id, TEST_USER_ID, db)
    assert state.session.status == "playing"

    # B joins mid-play and tries to bet -> rejected.
    await _join_seat(table.id, OTHER_USER_ID, db)
    with pytest.raises(HTTPException) as exc:
        await _deal_hand(table.id, OTHER_USER_ID, 1_000, db)
    assert exc.value.status_code == 409


async def test_ac6_out_of_turn_action_rejected(db):
    """During play only the current actor may act; the other seat 403s."""
    from fastapi import HTTPException

    table = await _setup_two_seated(db)
    await _deal_hand(table.id, TEST_USER_ID, 1_000, db)
    await _deal_hand(table.id, OTHER_USER_ID, 1_000, db)

    state = await _get_table_state(table.id, TEST_USER_ID, db)
    if state.session.status != "playing":
        pytest.skip("both dealt naturals — no turn to contest")

    actor = next(h for h in state.hands if h.move_deadline_at is not None)
    non_actor_id = OTHER_USER_ID if actor.user_id == TEST_USER_ID else TEST_USER_ID

    with pytest.raises(HTTPException) as exc:
        await _take_action(table.id, non_actor_id, "stand", db)
    assert exc.value.status_code == 403
