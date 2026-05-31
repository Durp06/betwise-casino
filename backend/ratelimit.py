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


# `storage_uri` defaults to in-memory (fine for the single-worker Railway
# container). Point BETWISE_RATELIMIT_STORAGE at a Redis URL when running
# multiple workers/replicas so the per-user counters are shared rather than
# per-process (otherwise the effective limit is N× the configured value).
limiter = Limiter(
    key_func=_rate_limit_key,
    storage_uri=os.environ.get("BETWISE_RATELIMIT_STORAGE", "memory://"),
)

# Tunable per environment. Tests set these to a high number to avoid
# tripping the limit during normal test runs.
ADVICE_RATE_LIMIT = os.environ.get("BETWISE_ADVICE_RATE_LIMIT", "10/minute")

# Per-user throttle for state-mutating / compute-heavy game endpoints
# (deal/act/join/leave/state across holdem + poker + blackjack). A DB-connection
# / DoS guard, not a billing cap. Generous enough for the 3-second client poll
# (~20/min) plus normal play; env-tunable so the test suite (which hammers these
# in tight loops) can disable it and ops can tighten in production.
MUTATION_RATE_LIMIT = os.environ.get("BETWISE_MUTATION_RATE_LIMIT", "120/minute")
