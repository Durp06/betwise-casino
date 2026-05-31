"""
main.py — FastAPI app assembly for BetWise Casino.

Design constraints (specs/betwise-casino.md §T15):
- GET /api/health works without DB (Railway healthcheck).
- Startup event does NOT touch the DB; JWKS pre-warm is try/except.
- frontend/dist mount tolerates missing directory (warn, don't crash).
- Global exception handler: returns {"detail": "Internal server error"},
  logs traceback server-side, never leaks to client.
- CORS reads origin from env; defaults to localhost:5173 for local dev.
- Importing this module does zero network IO and works with no env vars set.
"""

from __future__ import annotations

import logging
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.ratelimit import limiter
from backend.routers import users, tables, game, advice, leaderboard, analytics, sessions, poker_tables, poker_game, poker_advice, holdem

logger = logging.getLogger(__name__)

# ─── App construction ─────────────────────────────────────────────────────────

app = FastAPI(title="BetWise Casino", version="1.0.0")

# Register the shared slowapi limiter so route-level @limiter.limit(...)
# decorators can find it via app.state and the global 429 handler fires.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — read allowed origins from env; default to localhost for dev.
# Fail fast if anyone ever sets BETWISE_CORS_ORIGINS="*" — wildcard origins
# combined with allow_credentials=True is insecure (and browsers reject the
# response). Catching it at startup beats catching it during incident review.
_cors_origins = [
    o.strip()
    for o in os.environ.get("BETWISE_CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

if "*" in _cors_origins:
    raise RuntimeError(
        "BETWISE_CORS_ORIGINS contains '*' and allow_credentials=True — "
        "this combination is insecure and rejected by browsers. "
        "Set BETWISE_CORS_ORIGINS to an explicit comma-separated list of allowed origins."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global exception handler ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions, log traceback, return clean 500."""
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ─── Health endpoint (no DB touch) ────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
async def health() -> dict:
    """Railway healthcheck. Must return 200 even with no DB configured."""
    return {"status": "ok"}


# ─── Router registration ──────────────────────────────────────────────────────

app.include_router(users.router, prefix="/api")
app.include_router(tables.router, prefix="/api")
app.include_router(game.router, prefix="/api")
app.include_router(advice.router, prefix="/api")
app.include_router(leaderboard.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(poker_tables.router, prefix="/api")
app.include_router(poker_game.router, prefix="/api")
app.include_router(poker_advice.router, prefix="/api")
app.include_router(holdem.router, prefix="/api")


# ─── Startup event ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup() -> None:
    """Pre-warm JWKS cache; tolerate failures so boot works without Supabase."""
    try:
        from backend.auth import _fetch_jwks  # noqa: PLC0415
        await _fetch_jwks()
    except Exception:
        logger.warning("Could not pre-warm JWKS cache on startup (ok for local dev)")


# ─── Static frontend mount (LAST — so API routes win) ─────────────────────────

_frontend_dist = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),  # betwise-casino/
    "frontend",
    "dist",
)

if os.path.isdir(_frontend_dist):
    # Serve hashed assets (Vite emits /assets/index-*.js etc.) via StaticFiles
    # mounted at /assets. The static mount handles those file requests cleanly.
    _assets_dir = os.path.join(_frontend_dist, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    # SPA fallback: any non-/api/* path returns index.html so React Router
    # owns client-side routing (refreshing /lobby, deep-linking /profile, etc.
    # all work). Specific files at the top level (favicon.ico, robots.txt) are
    # served from disk if they exist.
    from fastapi.responses import FileResponse  # noqa: PLC0415

    _index_html = os.path.join(_frontend_dist, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API routes are already matched above this catch-all; we only get here
        # for non-/api paths. Reject /api/* defensively in case ordering changes.
        if full_path.startswith("api/") or full_path.startswith("api"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        # Try the literal file (e.g. favicon.ico, robots.txt at dist root)
        candidate = os.path.join(_frontend_dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        # Otherwise serve the SPA shell; React Router takes over client-side.
        return FileResponse(_index_html)
else:
    logger.warning(
        "frontend/dist not found at %s — frontend not served. "
        "Run `npm run build` inside betwise-casino/frontend/ to build it.",
        _frontend_dist,
    )
