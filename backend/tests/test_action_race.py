"""
test_action_race.py — regression test for CSO Finding #3.

Verifies that the SELECT … FOR UPDATE lock on the Hand row in _take_action
prevents double-mutation under concurrent requests.

Two tests:

1. test_take_action_query_uses_with_for_update  (structural / compile-time)
   Inspects the source of _take_action and asserts both the Hand SELECT and the
   User SELECT for doubling call .with_for_update().  This guards against
   accidental removal of the lock in future refactors.

2. test_sequential_hits_are_idempotent_after_stand  (behavioural)
   Fires two sequential hit requests where the first hit causes a stand/bust,
   then asserts the second request is rejected (400/403/404).  This validates
   the existing legality checks that the lock enables — the second concurrent
   transaction would see a non-active hand and bail.

Note on true concurrent testing: the test suite uses a single shared
AsyncSession per test (StaticPool, in-memory SQLite).  Two asyncio coroutines
sharing one session produce ResourceClosedError when both try to flush
simultaneously — not a real race, just a test-harness artefact.  The actual
production race is Postgres-specific and is addressed by .with_for_update() at
the ORM layer.  The structural test above gives the regression guarantee.
"""
from __future__ import annotations

import inspect

import pytest

from tests.conftest import TEST_USER_ID, seed_hand, seed_session, seed_table, seed_user


# ─── Structural test ─────────────────────────────────────────────────────────

def test_take_action_query_uses_with_for_update():
    """_take_action must call .with_for_update() on both the Hand SELECT and the
    User SELECT used for doubling.  CSO Finding #3 regression guard.
    """
    from backend.routers.game import _take_action  # noqa: PLC0415

    source = inspect.getsource(_take_action)

    # with_for_update() must appear at least twice:
    # once on the Hand query, once on the User query for doubling.
    occurrences = source.count("with_for_update")
    assert occurrences >= 2, (
        f"Expected at least 2 calls to .with_for_update() in _take_action "
        f"(one on Hand SELECT, one on User SELECT for double); found {occurrences}. "
        "CSO Finding #3: without row-level locking, two concurrent requests "
        "from the same user can both pass the turn check under Postgres "
        "READ COMMITTED and both mutate the hand / chip balance."
    )


# ─── Behavioural test ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_second_hit_after_stand_is_rejected(client, db):
    """After the first hit causes the hand to stand/bust, a second hit must be
    rejected with a non-200 status code.

    This validates the legality-check path that the FOR UPDATE lock enables in
    production: the second concurrent transaction waits for the first to commit,
    then reads the updated hand status and bails.

    In the test suite the two requests are sequential (one await after another),
    but the behavioural assertion — second request rejected — is the same as
    what happens under the lock in Postgres.
    """
    await seed_user(db, TEST_USER_ID, "race_sequential_user", chip_balance=100_000)
    table = await seed_table(db, name="Race Sequential Table")

    # Deck with exactly one card so the first hit leaves the deck empty.
    # Hand total after hit: 5+6+3 = 14 — still active (not bust, not stand).
    # We want two hits to work in sequence to test the deck depletion path,
    # OR we use a hand that will immediately bust/stand after the first hit.
    # Use a near-bust hand: 10 + 9 = 19. Hitting with any card >= 3 busts it.
    near_bust_deck = [
        {"suit": "clubs", "value": "5"},   # this will bust the 19-total hand
        {"suit": "diamonds", "value": "4"},
    ]
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
        deck_state=near_bust_deck,
    )
    # 10 + 9 = 19; hitting 5 gives 24 — bust
    await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[
            {"suit": "hearts", "value": "10"},
            {"suit": "spades", "value": "9"},
        ],
        bet=1_000,
        status="active",
    )

    # First request: should succeed (hit, hand goes bust)
    resp1 = await client.post(
        f"/api/tables/{table.id}/action", json={"action": "hit"}
    )
    assert resp1.status_code == 200, (
        f"First hit should succeed; got {resp1.status_code}: {resp1.text}"
    )
    data1 = resp1.json()
    assert data1["status"] == "bust", (
        f"Expected hand to bust after hitting 19-total hand; got status={data1['status']}, "
        f"cards={data1['cards']}"
    )
    assert len(data1["cards"]) == 3, (
        f"Expected 3 cards after first hit; got {len(data1['cards'])}: {data1['cards']}"
    )

    # Second request: the hand is now bust — it is no longer the player's turn.
    # The handler must reject this with 400, 403, or 404.
    resp2 = await client.post(
        f"/api/tables/{table.id}/action", json={"action": "hit"}
    )
    assert resp2.status_code in (400, 403, 404), (
        f"Second hit on a bust hand must be rejected; got {resp2.status_code}: {resp2.text}"
    )


@pytest.mark.asyncio
async def test_hand_has_exactly_one_extra_card_after_single_successful_hit(client, db):
    """Regression: a single hit adds exactly 1 card, not 2.

    Sanity-checks that the deck mutation in _take_action is atomic — only one
    card is popped per successful action.  If the row lock were missing and two
    requests both read the same deck snapshot, they could each pop the same
    'first' card and write it back independently, producing duplicate cards.
    """
    await seed_user(db, TEST_USER_ID, "race_card_count_user", chip_balance=100_000)
    table = await seed_table(db, name="Card Count Table")
    controlled_deck = [
        {"suit": "clubs", "value": "3"},
        {"suit": "diamonds", "value": "4"},
        {"suit": "hearts", "value": "5"},
    ]
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
        deck_state=controlled_deck,
    )
    await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[
            {"suit": "hearts", "value": "5"},
            {"suit": "spades", "value": "6"},
        ],
        bet=1_000,
        status="active",
    )

    resp = await client.post(
        f"/api/tables/{table.id}/action", json={"action": "hit"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Must have exactly 3 cards — the two dealt at start plus the one hit card
    assert len(data["cards"]) == 3, (
        f"Expected exactly 3 cards after one hit; got {len(data['cards'])}: {data['cards']}"
    )
    # The new card must be the first card from the deck (clubs/3)
    assert data["cards"][2] == {"suit": "clubs", "value": "3"}, (
        f"Expected third card to be clubs/3 (top of controlled deck); "
        f"got {data['cards'][2]}"
    )
