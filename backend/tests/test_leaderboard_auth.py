"""
test_leaderboard_auth.py — T8 (L3) Leaderboard requires auth.

AC-8.1: GET /api/leaderboard with a valid auth (the `client` fixture) returns 200
        and the existing top-N rows (response shape unchanged).
AC-8.2: GET /api/leaderboard with no authenticated user is rejected with 401/403
        (currently returns 200 anonymously — the vulnerability).

These tests FAIL until `get_leaderboard` in backend/routers/leaderboard.py
adds `current_user: CurrentUser` to its handler signature.

Strategy for AC-8.2: the test spins up an AsyncClient with NO auth dependency
override (so get_current_user runs its real logic) but with BETWISE_DEV_USER_ID
unset — since BETWISE_DEV_USER_ID IS set in the environment for the entire test
suite (conftest sets it), we need a client that uses a different override that
raises HTTPException(401).  This mirrors the "no token" attack.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import TEST_USER_ID, seed_user


# ─── AC-8.1 — authenticated request returns 200 ──────────────────────────────

@pytest.mark.asyncio
async def test_leaderboard_returns_200_for_authenticated_user(client, db):
    """AC-8.1: GET /api/leaderboard with the normal `client` (TEST_USER_ID) must
    return 200 and a list (possibly empty).  Shape regression guard.
    """
    await seed_user(db, TEST_USER_ID, "leaderboard_user", chip_balance=100_000)

    resp = await client.get("/api/leaderboard")
    assert resp.status_code == 200, (
        f"Expected 200 from leaderboard with valid auth; got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert isinstance(body, list), (
        f"Expected leaderboard response to be a list; got {type(body)}"
    )
    # If the seeded user is there, validate basic shape
    if body:
        first = body[0]
        assert "chip_balance" in first, f"Expected 'chip_balance' in row; got {first}"
        assert "username" in first, f"Expected 'username' in row; got {first}"


# ─── AC-8.2 — unauthenticated request is rejected ────────────────────────────

@pytest_asyncio.fixture
async def anon_client(db):
    """An AsyncClient with NO authenticated user — get_current_user raises 401."""
    from fastapi import HTTPException  # noqa: PLC0415
    from backend.main import app  # noqa: PLC0415
    from backend.auth import get_current_user  # noqa: PLC0415
    from backend.database import get_db  # noqa: PLC0415

    async def _no_auth():
        raise HTTPException(status_code=401, detail="Not authenticated")

    async def _override_db():
        yield db

    app.dependency_overrides[get_current_user] = _no_auth
    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_leaderboard_rejects_unauthenticated_request(anon_client):
    """AC-8.2: GET /api/leaderboard with no authenticated user must return
    a non-200 status (401 or 403).

    Currently the endpoint has no CurrentUser dependency, so it returns 200
    anonymously — this test confirms that the fix adds auth.
    """
    resp = await anon_client.get("/api/leaderboard")
    assert resp.status_code in (401, 403), (
        f"Expected 401/403 for unauthenticated leaderboard request; "
        f"got {resp.status_code}: {resp.text}.  "
        "The leaderboard endpoint must require authentication (add CurrentUser dep)."
    )
