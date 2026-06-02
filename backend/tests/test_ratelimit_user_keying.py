"""
test_ratelimit_user_keying.py — regression for the per-user rate-limit keying fix.

Guards PR6 security finding P5/N1/N2: the per-user rate limits silently keyed on
the client IP because route handlers set ``request.state.user_id`` *inside* the
handler body — AFTER slowapi had already evaluated the limiter key. The fix makes
``backend.auth.get_current_user`` accept the ``Request`` and stamp
``request.state.user_id`` (in BOTH the dev-bypass and JWT-success paths) BEFORE it
returns. Because it is a FastAPI dependency it resolves before slowapi's wrapper
body runs, so ``backend.ratelimit._rate_limit_key`` sees the user id and keys
per-user instead of per-proxy-IP.

Two layers, both deterministic and offline (no DB, no network):

(a) Unit — ``get_current_user`` stamps ``request.state.user_id`` with the dev UUID
    string when BETWISE_DEV_USER_ID is set.
(b) Unit — ``_rate_limit_key`` returns that user id when ``request.state.user_id``
    is set, and falls back to the remote address only when it is unset.

These assert the CORRECT post-fix behavior; they will fail until the auth.py fix
lands, which is intended.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from backend.auth import get_current_user
from backend.ratelimit import _rate_limit_key

DEV_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _fake_request(*, user_id: str | None = None, client_host: str | None = None) -> SimpleNamespace:
    """Build a minimal stand-in for starlette.Request.

    Only the attributes the code under test touches are populated:
      - ``state`` (with optional ``user_id``) — read by _rate_limit_key, written by
        get_current_user.
      - ``client`` (with ``host``) — read by slowapi's get_remote_address fallback.
    """
    state = SimpleNamespace()
    if user_id is not None:
        state.user_id = user_id
    client = SimpleNamespace(host=client_host) if client_host is not None else None
    return SimpleNamespace(state=state, client=client)


# ─── (a) get_current_user stamps request.state.user_id (dev-bypass path) ─────


@pytest.mark.asyncio
async def test_get_current_user_stamps_user_id_on_request_state(monkeypatch):
    """Dev-bypass path must set request.state.user_id to the dev UUID string.

    This is the load-bearing fix: the stamp has to happen inside the dependency
    (before slowapi reads the key), not inside the handler body (after).
    """
    monkeypatch.setenv("BETWISE_DEV_USER_ID", str(DEV_UUID))
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    request = _fake_request()
    result = await get_current_user(request=request, authorization=None)

    assert result == DEV_UUID
    # The stamp must be a string (slowapi keys on str), matching the dev UUID.
    assert getattr(request.state, "user_id", None) == str(DEV_UUID)
    assert isinstance(request.state.user_id, str)


# ─── (b) _rate_limit_key keys on the user id, falls back to IP ───────────────


def test_rate_limit_key_uses_user_id_when_set():
    """When request.state.user_id is set, the limiter key is that user id."""
    request = _fake_request(user_id=str(DEV_UUID), client_host="203.0.113.7")

    # Keys on the user, NOT the proxy IP — the whole point of the fix.
    assert _rate_limit_key(request) == str(DEV_UUID)


def test_rate_limit_key_falls_back_to_remote_address_when_unset():
    """With no request.state.user_id, the key falls back to the remote address."""
    request = _fake_request(user_id=None, client_host="203.0.113.7")

    assert _rate_limit_key(request) == "203.0.113.7"


def test_rate_limit_key_falls_back_to_loopback_when_no_client():
    """No user id and no client info → slowapi's 127.0.0.1 default."""
    request = _fake_request(user_id=None, client_host=None)

    assert _rate_limit_key(request) == "127.0.0.1"


@pytest.mark.asyncio
async def test_stamped_request_then_keyed_per_user(monkeypatch):
    """End-to-end of the two units: stamp via get_current_user, then key on it.

    Proves the stamp written by the dependency is exactly what the limiter reads,
    so a per-user counter — not a per-IP counter — is incremented.
    """
    monkeypatch.setenv("BETWISE_DEV_USER_ID", str(DEV_UUID))
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    request = _fake_request(client_host="203.0.113.7")
    await get_current_user(request=request, authorization=None)

    # Despite a non-loopback client IP, the key is the user id, not the IP.
    assert _rate_limit_key(request) == str(DEV_UUID)
