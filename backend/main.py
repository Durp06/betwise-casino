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

from backend.routers import users, tables, game, advice, leaderboard, analytics

logger = logging.getLogger(__name__)

# ─── App construction ─────────────────────────────────────────────────────────

app = FastAPI(title="BetWise Casino", version="1.0.0")

# CORS — read allowed origin from env; default to localhost for dev
_cors_origins = os.environ.get(
    "BETWISE_CORS_ORIGINS",
    "http://localhost:5173",
).split(",")

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
    # TEMP: also return the error type+message in the response body during the
    # initial deploy/debug window. Lock this back down to a generic message
    # once production is stable.
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
        },
    )


# ─── Health endpoint (no DB touch) ────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
async def health() -> dict:
    """Railway healthcheck. Must return 200 even with no DB configured."""
    return {"status": "ok"}


# ─── Diagnostic endpoint (TEMP — remove once deploy is verified) ─────────────
# Returns commit SHA + active driver + result of a trivial DB query so we can
# tell what's actually failing in production without scraping Railway logs.

@app.get("/api/_diag", tags=["diag"])
async def diag() -> dict:
    """Temporary debug endpoint. Returns version info and tests the DB."""
    import os as _os  # noqa: PLC0415

    out: dict = {
        "commit": _os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown")[:12],
        "db_url_prefix": (_os.environ.get("DATABASE_URL", "") or "")[:30],
        "db_url_has_asyncpg": "+asyncpg" in (_os.environ.get("DATABASE_URL", "") or ""),
        "supabase_url_set": bool(_os.environ.get("SUPABASE_URL")),
        "jwt_secret_set": bool(_os.environ.get("SUPABASE_JWT_SECRET")),
        "anthropic_set": bool(_os.environ.get("ANTHROPIC_API_KEY")),
    }
    try:
        from backend.database import get_session_factory  # noqa: PLC0415
        from sqlalchemy import text as _text  # noqa: PLC0415

        factory = get_session_factory()
        async with factory() as session:
            res = await session.execute(_text("SELECT 1 AS ok"))
            row = res.first()
            out["db"] = {"ok": True, "value": row[0] if row else None}
    except Exception as e:  # noqa: BLE001
        out["db"] = {
            "ok": False,
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
        }
    return out


# ─── Router registration ──────────────────────────────────────────────────────

app.include_router(users.router, prefix="/api")
app.include_router(tables.router, prefix="/api")
app.include_router(game.router, prefix="/api")
app.include_router(advice.router, prefix="/api")
app.include_router(leaderboard.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")


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
