"""
test_advice_ratelimit.py — slowapi limit on /api/advice/{hand_id} and /pre.

Covers CSO Finding #2 (LLM cost amplification). Each advice call hits
Anthropic at ~$0.005, so without a rate limit a single authenticated user
can deplete the API budget via rapid requests against their own hand_id.
The endpoints are decorated with @limiter.limit("10/minute") (configurable
via BETWISE_ADVICE_RATE_LIMIT env var); when exceeded the request returns
429 Too Many Requests.

These tests fire >10 requests in quick succession and assert at least one
returns 429.
"""
from __future__ import annotations

import pytest

from tests.conftest import (
    TEST_USER_ID,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


@pytest.mark.asyncio
async def test_post_advice_rate_limit_kicks_in(client, db, mock_anthropic):
    """11+ requests trigger the 10/minute slowapi guard with at least one 429."""
    await seed_user(db, TEST_USER_ID, "rate_test_post", chip_balance=100_000)
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
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    statuses = []
    for _ in range(12):
        resp = await client.post(
            f"/api/advice/{hand.id}",
            json={"player_guess": "hit"},
        )
        # Drain so the streaming generator completes.
        _ = resp.text
        statuses.append(resp.status_code)

    assert 429 in statuses, (
        f"Expected at least one 429 within 12 requests; got statuses: {statuses}"
    )


@pytest.mark.asyncio
async def test_pre_advice_rate_limit_kicks_in(client, db, mock_anthropic):
    """Pre-advice endpoint is also limited (same key, separate bucket per route)."""
    await seed_user(db, TEST_USER_ID, "rate_test_pre", chip_balance=100_000)
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
        cards=[{"suit": "hearts", "value": "5"}, {"suit": "spades", "value": "6"}],
        status="active",
    )

    statuses = []
    for _ in range(12):
        resp = await client.post(f"/api/advice/{hand.id}/pre")
        _ = resp.text
        statuses.append(resp.status_code)

    assert 429 in statuses, (
        f"Expected at least one 429 within 12 requests; got statuses: {statuses}"
    )
