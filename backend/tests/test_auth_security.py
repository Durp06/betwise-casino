"""
test_auth_security.py — JWT aud/iss validation + dev bypass prod guard.

Covers CSO Findings #4 and #7:
- Finding #4: jwt.decode now requires aud="authenticated" and (when
  SUPABASE_URL is set) iss matching that URL. Tokens that pass signature
  but fail those claims are rejected.
- Finding #7: BETWISE_DEV_USER_ID combined with ENVIRONMENT=production
  returns 503 instead of authenticating as the dev user — guards against
  accidentally promoting the CI test env into Railway.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

from backend.auth import get_current_user


# ─── Finding #7: dev bypass prod guard ──────────────────────────────────────


@pytest.mark.asyncio
async def test_dev_bypass_rejected_in_production(monkeypatch):
    """BETWISE_DEV_USER_ID + ENVIRONMENT=production → 503 misconfig."""
    monkeypatch.setenv("BETWISE_DEV_USER_ID", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=None)
    assert exc.value.status_code == 503
    assert "misconfigured" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_dev_bypass_still_works_without_environment(monkeypatch):
    """No ENVIRONMENT var = dev bypass works (test/CI path)."""
    monkeypatch.setenv("BETWISE_DEV_USER_ID", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    result = await get_current_user(authorization=None)
    assert result == uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.mark.asyncio
async def test_dev_bypass_works_in_staging(monkeypatch):
    """ENVIRONMENT=staging does NOT trigger the prod guard."""
    monkeypatch.setenv("BETWISE_DEV_USER_ID", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    monkeypatch.setenv("ENVIRONMENT", "staging")

    result = await get_current_user(authorization=None)
    assert result == uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


# ─── Finding #4: JWT audience + issuer validation ───────────────────────────


def _make_token(payload: dict, secret: str = "test-secret-do-not-use") -> str:
    """Forge an HS256 token for testing — we control the secret."""
    return jose_jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.asyncio
async def test_jwt_wrong_audience_rejected(monkeypatch):
    """Token with aud='wrong' is rejected even with valid signature."""
    monkeypatch.delenv("BETWISE_DEV_USER_ID", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-do-not-use")
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    token = _make_token({
        "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "aud": "service_role",  # wrong audience — should be "authenticated"
    })

    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_jwt_wrong_issuer_rejected(monkeypatch):
    """When SUPABASE_URL is set, iss claim must match."""
    monkeypatch.delenv("BETWISE_DEV_USER_ID", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-do-not-use")
    monkeypatch.setenv("SUPABASE_URL", "https://right.supabase.co")

    token = _make_token({
        "sub": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "aud": "authenticated",
        "iss": "https://wrong.supabase.co/auth/v1",  # wrong issuer
    })

    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_jwt_correct_claims_accepted(monkeypatch):
    """Valid signature + correct aud + correct iss → returns the sub UUID."""
    monkeypatch.delenv("BETWISE_DEV_USER_ID", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-do-not-use")
    monkeypatch.setenv("SUPABASE_URL", "https://right.supabase.co")

    expected_sub = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    token = _make_token({
        "sub": expected_sub,
        "aud": "authenticated",
        "iss": "https://right.supabase.co/auth/v1",
    })

    result = await get_current_user(authorization=f"Bearer {token}")
    assert result == uuid.UUID(expected_sub)


@pytest.mark.asyncio
async def test_jwt_no_supabase_url_skips_issuer_check(monkeypatch):
    """No SUPABASE_URL env = iss claim is not validated (local dev path)."""
    monkeypatch.delenv("BETWISE_DEV_USER_ID", raising=False)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-do-not-use")
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    expected_sub = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    token = _make_token({
        "sub": expected_sub,
        "aud": "authenticated",
        # no iss claim at all
    })

    result = await get_current_user(authorization=f"Bearer {token}")
    assert result == uuid.UUID(expected_sub)
