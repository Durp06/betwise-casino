# ─── Stage 1: build the React frontend ───────────────────────────────────────
FROM node:20-alpine AS frontend-builder

# Vite reads VITE_* vars at build time and bakes them into the bundle, so we
# need them as build args. Railway passes all env vars as ARGs automatically.
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
ENV VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY}

WORKDIR /build
# Copy package manifests first so the install layer caches across source changes
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build
# Produces /build/dist


# ─── Stage 2: backend runtime ────────────────────────────────────────────────
FROM python:3.11-slim

# Avoid pyc clutter and ensure stdout flushes for Railway logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Mark this image as the production runtime. This activates two fail-safes that
# are otherwise dormant (they key off ENVIRONMENT=production):
#   - auth.py refuses the BETWISE_DEV_USER_ID dev-bypass (returns 503) so a
#     stray dev var can never silently authenticate every request as one user.
#   - database.py refuses the in-memory SQLite fallback when DATABASE_URL is
#     missing, failing the deploy loudly instead of booting a throwaway DB.
# Tests and the Playwright e2e harness run OUTSIDE this image, so they are
# unaffected. NOTE: do NOT set BETWISE_DEV_USER_ID in the Railway production
# environment — combined with this flag it will (intentionally) 503 the service.
ENV ENVIRONMENT=production

WORKDIR /app

# Install backend dependencies (cached layer if requirements.txt unchanged)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Bring the pre-built frontend bundle from stage 1
# (main.py resolves `frontend/dist` relative to `__file__`, so this layout matches)
COPY --from=frontend-builder /build/dist ./frontend/dist

# Create a non-root user and hand it ownership of /app.
# Railway also sandboxes containers, but defense-in-depth — don't run as root.
RUN useradd --create-home --shell /bin/bash --uid 1000 app \
    && chown -R app:app /app
USER app

# Run uvicorn from /app so absolute imports `from backend.X import …` resolve.
# PORT is injected by Railway; fall back to 8000 for local docker run.
#
# Apply pending DB migrations BEFORE starting the server. `backend.migrate`
# is idempotent (ledger + IF NOT EXISTS guards) and exits non-zero if a
# migration fails, so a bad migration fails the deploy loudly instead of
# booting a half-migrated app. With no DATABASE_URL set it no-ops and uvicorn
# still starts (health-only boots). This replaces the old hand-run
# `railway run ... migrate` step that was routinely forgotten.
EXPOSE 8000
CMD ["sh", "-c", "python -m backend.migrate && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
