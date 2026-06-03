"""
test_advice_streak_idempotency.py — T4 (M2) Streak inflation via advice replay.

AC-4.1 (happy path): first legitimate advice call with a correct guess increments
        current_streak by exactly 1.
AC-4.2 (replay blocked): two sequential advice calls for the same hand_id with
        hand.cards UNCHANGED and a correct guess increase current_streak by at most 1.
AC-4.3 (ownership unchanged): requesting advice for another user's hand returns 403.
AC-4.4 (multi-decision NOT over-blocked): two advice calls on the same hand_id where
        hand.cards changes between them (simulating a real hit) increment current_streak
        by 2 (once per distinct card-count decision).

These tests FAIL until the idempotency key `(hand_id, len(hand.cards))` is
implemented in advice.py and the `advice_graded_card_count` column is added to Hand.
"""
from __future__ import annotations

import json

import pytest

from tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


# ─── SSE parsing helper ───────────────────────────────────────────────────────

def _parse_final_event(text: str) -> dict:
    """Extract the final SSE JSON event (the summary payload) from the raw response text."""
    final: dict = {}
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
                if isinstance(payload, dict) and "optimal_action" in payload:
                    final = payload
            except json.JSONDecodeError:
                pass
    return final


# ─── AC-4.1 — happy path: first correct guess increments streak by 1 ─────────

@pytest.mark.asyncio
async def test_advice_first_correct_guess_increments_streak(client, db, mock_anthropic):
    """AC-4.1: a first, legitimate advice call with a correct guess must increment
    current_streak by exactly 1 (from 0 to 1) and update best_streak.
    """
    user = await seed_user(db, TEST_USER_ID, "streak_happy_user", chip_balance=100_000)
    assert user.current_streak == 0

    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    # Hard 8 vs 6 — optimal is hit; player guesses hit → correct
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "3"}],
        status="active",
    )

    resp = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "hit"},
    )
    assert resp.status_code == 200, resp.text
    final = _parse_final_event(resp.text)
    assert final, "Expected a final SSE summary event with 'optimal_action'"

    # Streak must have incremented by 1
    assert final["current_streak"] == 1, (
        f"Expected current_streak=1 after first correct guess; got {final['current_streak']}"
    )
    assert final["best_streak"] >= 1, (
        f"Expected best_streak >= 1; got {final['best_streak']}"
    )


# ─── AC-4.2 — replay blocked: same hand, unchanged cards → no second streak bump ──

@pytest.mark.asyncio
async def test_advice_replay_does_not_pump_streak(client, db, mock_anthropic):
    """AC-4.2: two sequential advice calls for the same hand_id with hand.cards
    UNCHANGED (a replay) must increase current_streak by at most 1 total.
    """
    await seed_user(db, TEST_USER_ID, "streak_replay_user", chip_balance=100_000)

    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "3"}],
        status="active",
    )

    # First call — correct guess, streak goes to 1
    resp1 = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "hit"},
    )
    assert resp1.status_code == 200, resp1.text
    final1 = _parse_final_event(resp1.text)
    streak_after_first = final1.get("current_streak", -999)

    # Second call — same hand_id, same cards (replay), same correct guess
    # Must NOT increment streak again
    resp2 = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "hit"},
    )
    assert resp2.status_code == 200, resp2.text
    final2 = _parse_final_event(resp2.text)
    streak_after_second = final2.get("current_streak", -999)

    assert streak_after_second == streak_after_first, (
        f"Replay must not pump the streak: after first call streak={streak_after_first}, "
        f"after replay streak={streak_after_second} (should be equal)"
    )


# ─── AC-4.3 — ownership unchanged: other user's hand returns 403 ─────────────

@pytest.mark.asyncio
async def test_advice_for_other_users_hand_returns_403(client, db, mock_anthropic):
    """AC-4.3: requesting advice for a hand owned by OTHER_USER_ID via TEST_USER_ID's
    client must return 403 (the ownership check at advice.py:99-100 is not regressed).
    """
    await seed_user(db, TEST_USER_ID, "streak_owner_user", chip_balance=100_000)
    other = await seed_user(db, OTHER_USER_ID, "streak_other_user", chip_balance=100_000)

    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    # Hand owned by OTHER_USER_ID
    other_hand = await seed_hand(
        db,
        session.id,
        other.id,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "3"}],
        status="active",
    )

    # client is authenticated as TEST_USER_ID
    resp = await client.post(
        f"/api/advice/{other_hand.id}",
        json={"player_guess": "hit"},
    )
    assert resp.status_code == 403, (
        f"Expected 403 for advice on another user's hand; got {resp.status_code}: {resp.text}"
    )


# ─── AC-4.4 — multi-decision NOT over-blocked: changing cards → second bump ─────

@pytest.mark.asyncio
async def test_advice_two_decisions_different_card_counts_increment_streak_twice(
    client, db, mock_anthropic
):
    """AC-4.4: two advice calls on the same hand_id where hand.cards changes between
    them (simulating a real hit: cards grow from 2 to 3) must increment current_streak
    by 2 (once per distinct card-count decision).

    This proves the fix keys on `len(hand.cards)`, not hand identity — a boolean
    'already advised' flag would fail this test by over-blocking the second decision.
    """
    await seed_user(db, TEST_USER_ID, "streak_multidecision_user", chip_balance=100_000)

    table = await seed_table(db)
    session = await seed_session(
        db,
        table.id,
        status="playing",
        dealer_cards=[{"suit": "hearts", "value": "6"}],
    )
    # Start with 2 cards (hard 8 vs 6 — optimal: hit)
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "3"}],
        status="active",
    )

    # First advice call — 2-card hand, correct guess (hit)
    resp1 = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "hit"},
    )
    assert resp1.status_code == 200, resp1.text
    final1 = _parse_final_event(resp1.text)
    streak_after_first = final1.get("current_streak", -999)

    # Simulate a real hit: mutate the hand's cards from 2 → 3 cards via the db fixture
    from sqlalchemy import select  # noqa: PLC0415
    from backend.models import Hand  # noqa: PLC0415

    hand_row = (await db.execute(select(Hand).where(Hand.id == hand.id))).scalar_one()
    new_cards = list(hand_row.cards) + [{"suit": "clubs", "value": "2"}]
    hand_row.cards = new_cards
    await db.flush()

    # Second advice call — now 3-card hand (hard 10 vs 6 — optimal: double or hit)
    # Use "hit" as the guess which is correct for any 10-total hand
    resp2 = await client.post(
        f"/api/advice/{hand.id}",
        json={"player_guess": "hit"},
    )
    assert resp2.status_code == 200, resp2.text
    final2 = _parse_final_event(resp2.text)
    streak_after_second = final2.get("current_streak", -999)

    assert streak_after_second == streak_after_first + 1, (
        f"Two decisions with distinct card counts must each bump the streak: "
        f"after first={streak_after_first}, after second={streak_after_second} "
        f"(expected {streak_after_first + 1}).  "
        f"A boolean 'already advised' flag would cause streak_after_second == streak_after_first, "
        f"which is the over-blocking regression this AC guards against."
    )
