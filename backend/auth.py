"""
auth.py — Supabase JWT verification for BetWise Casino.

Design constraints (specs/betwise-casino.md §T9):
- Module-level _JWKS_CACHE is empty at import (no network at import time).
- JWKS is fetched lazily on first authenticated request.
- BETWISE_DEV_USER_ID env var bypasses JWT verification for local dev/tests.
- Invalid tokens return 401 with clean message — never leak jose errors.
- Importing this module does zero network IO.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any

import httpx
from fastapi import Depends, Header, HTTPException
from jose import jwt

# ─── Module-level JWKS cache ─────────────────────────────────────────────────
# Empty at import time; populated lazily on first JWT verification call.
_JWKS_CACHE: dict[str, Any] = {}


async def _fetch_jwks() -> dict:
    """Lazily fetch and cache the Supabase JWKS.

    On first call, fetches from SUPABASE_URL/.well-known/jwks.json and caches.
    On subsequent calls, returns from cache.
    """
    if _JWKS_CACHE:
        return _JWKS_CACHE

    supabase_url = os.environ.get("SUPABASE_URL", "")
    if not supabase_url:
        # No Supabase URL — can't fetch JWKS; will fall back to JWT secret
        return {}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{supabase_url}/auth/v1/.well-known/jwks.json",
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            _JWKS_CACHE.update(data)
            return _JWKS_CACHE
    except Exception:
        # Network failure or bad Supabase URL — return empty, fallback to secret
        return {}


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> uuid.UUID:
    """FastAPI dependency: verify JWT and return the user UUID.

    Test bypass: if BETWISE_DEV_USER_ID env var is set, skip verification
    and return that UUID directly. Documented in CLAUDE.md.

    Raises HTTPException(401) on any auth failure with a clean message.
    """
    # ── Dev/test bypass ──────────────────────────────────────────────────────
    # CRITICAL: refuse the dev bypass in production. CI sets BETWISE_DEV_USER_ID
    # for tests; production must NOT. Operators set ENVIRONMENT=production in
    # Railway. If both are set together, the service is misconfigured — fail
    # loud rather than silently authenticating every request as the dev user.
    dev_user_id = os.environ.get("BETWISE_DEV_USER_ID")
    if dev_user_id and os.environ.get("ENVIRONMENT", "").lower() == "production":
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).critical(
            "BETWISE_DEV_USER_ID set in production environment — rejecting all "
            "requests until this is unset. This would bypass authentication entirely."
        )
        raise HTTPException(status_code=503, detail="Service misconfigured")

    if dev_user_id:
        try:
            return uuid.UUID(dev_user_id)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    # ── Production JWT verification ──────────────────────────────────────────
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        # Inspect the token header to determine which algorithm to use
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")

        # Build aud + iss expectations from env. Supabase issues `aud:"authenticated"`
        # for end users and `iss:"{SUPABASE_URL}/auth/v1"`. When SUPABASE_URL is
        # unset (local dev), iss verification is skipped because there's no value
        # to compare against. aud is always verified.
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        expected_issuer = f"{supabase_url}/auth/v1" if supabase_url else None
        decode_kwargs = {
            "audience": "authenticated",
            "options": {"verify_aud": True, "verify_iss": bool(supabase_url)},
        }
        if expected_issuer is not None:
            decode_kwargs["issuer"] = expected_issuer

        if alg.startswith("HS"):
            # Symmetric secret (HS256 / HS384 / HS512)
            jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")
            if not jwt_secret:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=[alg],
                **decode_kwargs,
            )
        elif alg.startswith("RS") or alg.startswith("ES"):
            # Asymmetric key via JWKS (RS256 / RS384 / ES256 etc.)
            jwks = await _fetch_jwks()
            if not (jwks and jwks.get("keys")):
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            payload = jwt.decode(
                token,
                jwks,
                algorithms=[alg],
                **decode_kwargs,
            )
        else:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return uuid.UUID(str(sub))

    except HTTPException:
        raise
    except Exception:
        # Never leak underlying jose errors
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ─── Convenience alias ───────────────────────────────────────────────────────
CurrentUser = Annotated[uuid.UUID, Depends(get_current_user)]
