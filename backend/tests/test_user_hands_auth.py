"""
test_user_hands_auth.py — Regression tests for IDOR fix on GET /api/users/{id}/hands.

Three cases:
1. No auth header → 401
2. Authenticated as user A, requesting user B's hands → 403
3. Authenticated as owner requesting own hands → 200 with correct list
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    seed_hand,
    seed_session,
    seed_table,
    seed_user,
)


# Case 1: No Authorization header → 401
@pytest.mark.asyncio
async def test_user_hands_no_auth_returns_401(monkeypatch):
    """Without the dev-bypass env var, unauthenticated request must return 401."""
    monkeypatch.delenv("BETWISE_DEV_USER_ID", raising=False)

    from backend.main import app  # noqa: PLC0415

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as unauthenticated:
        resp = await unauthenticated.get(f"/api/users/{TEST_USER_ID}/hands")

    assert resp.status_code == 401


# Case 2: Authenticated as user A, requesting user B's hands → 403
@pytest.mark.asyncio
async def test_user_hands_cross_user_returns_403(other_client, db):
    """other_client is OTHER_USER_ID; requesting TEST_USER_ID's hands must return 403."""
    await seed_user(db, TEST_USER_ID, "handowner")
    await seed_user(db, OTHER_USER_ID, "snooper")

    # Seed a hand for TEST_USER_ID so there is something to find
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    await seed_hand(db, session.id, TEST_USER_ID, status="finished")

    # other_client (OTHER_USER_ID) asks for TEST_USER_ID's hands
    resp = await other_client.get(f"/api/users/{TEST_USER_ID}/hands")
    assert resp.status_code == 403, (
        f"Cross-user hand history access must return 403; got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", "")
    assert "another player" in detail.lower() or "cannot" in detail.lower(), (
        f"Expected ownership error message; got: {detail!r}"
    )


# Case 3: Owner requesting own hands → 200 with correct list
@pytest.mark.asyncio
async def test_user_hands_owner_returns_200(client, db):
    """TEST_USER_ID requesting their own hand history must return 200 and the seeded hands."""
    await seed_user(db, TEST_USER_ID, "selfviewer")
    table = await seed_table(db)
    session = await seed_session(db, table.id, status="finished")
    hand = await seed_hand(
        db,
        session.id,
        TEST_USER_ID,
        cards=[{"suit": "hearts", "value": "A"}, {"suit": "spades", "value": "K"}],
        bet=2_000,
        status="finished",
    )

    resp = await client.get(f"/api/users/{TEST_USER_ID}/hands")
    assert resp.status_code == 200, (
        f"Owner should get 200; got {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    assert isinstance(data, list), "Response must be a list"
    assert len(data) >= 1, "Expected at least the seeded hand in the response"
    # Verify the seeded hand appears in the response
    hand_ids = [str(h["id"]) for h in data]
    assert str(hand.id) in hand_ids, (
        f"Seeded hand {hand.id} not found in response: {hand_ids}"
    )
