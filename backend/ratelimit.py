"""
ratelimit.py — shared slowapi Limiter for the FastAPI app.

Pulled into its own module so backend/main.py and backend/routers/advice.py
can both import the SAME Limiter instance without a circular import. The
rate-limit decorator only enforces when the route also exposes `request:
Request` as a parameter so slowapi can look up `request.state` for the key.

Keying:
  - When `request.state.user_id` is set (the authenticated handler stuffs
    it there), the key is the user's UUID — per-user limits.
  - Otherwise, fall back to remote IP. Mostly relevant if a route ever
    exposes itself to unauthenticated traffic.

The default limit value is overridable via `BETWISE_ADVICE_RATE_LIMIT`
env var (default "10/minute") so tests can crank it without disabling the
guard, and ops can tighten it in production without a deploy.
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _rate_limit_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)

# Tunable per environment. Tests set this to a high number to avoid
# tripping the limit during normal test runs.
ADVICE_RATE_LIMIT = os.environ.get("BETWISE_ADVICE_RATE_LIMIT", "10/minute")
