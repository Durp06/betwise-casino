"""
test_reset_chips_balance.py — AC-B4, AC-B5.

Tests map 1:1 to acceptance criteria from specs/centralized-money-system.md §3
(Backend section).  All tests are EXPECTED to fail (red) until the implementation
updates reset_chips in backend/routers/users.py to use STARTING_BALANCE_CENTS.
"""

from __future__ import annotations

import pytest

from tests.conftest import TEST_USER_ID, seed_user


# ─── AC-B4: eligible user (balance < 1000) gets refilled to 5_000_000 ─────────

@pytest.mark.asyncio
async def test_reset_chips_eligible_refills_to_starting_balance(client, db) -> None:
    """AC-B4: POST /api/users/me/reset-chips for a user with chip_balance < 1000
    sets chip_balance to 5_000_000 (STARTING_BALANCE_CENTS), not the old 100_000.
    """
    # Seed a broke user who qualifies for a reset (balance 500 < 1000 threshold)
    await seed_user(db, TEST_USER_ID, "brokeuser", chip_balance=500)

    resp = await client.post("/api/users/me/reset-chips")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    assert data["chip_balance"] == 5_000_000, (
        f"reset-chips should refill to 5_000_000, got {data['chip_balance']}"
    )


# ─── AC-B5: ineligible user (balance >= 1000) gets 409 and no change ──────────

@pytest.mark.asyncio
async def test_reset_chips_ineligible_returns_409(client, db) -> None:
    """AC-B5: POST /api/users/me/reset-chips for a user with chip_balance >= 1000
    returns HTTP 409 and leaves the balance unchanged.
    """
    # Seed a user who is NOT eligible for a reset (balance 2000 >= 1000 threshold)
    await seed_user(db, TEST_USER_ID, "richuser", chip_balance=2000)

    resp = await client.post("/api/users/me/reset-chips")
    assert resp.status_code == 409, (
        f"expected HTTP 409 for ineligible reset, got {resp.status_code}: {resp.text}"
    )

    # Verify the balance was NOT changed — fetch the user and confirm
    me_resp = await client.get("/api/users/me")
    assert me_resp.status_code == 200, f"GET /api/users/me failed: {me_resp.text}"
    me_data = me_resp.json()
    assert me_data["chip_balance"] == 2000, (
        f"balance should remain 2000 after rejected reset, got {me_data['chip_balance']}"
    )
