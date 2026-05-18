# syntax=docker/dockerfile:1.7

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

WORKDIR /app

# Install backend dependencies (cached layer if requirements.txt unchanged)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Bring the pre-built frontend bundle from stage 1
# (main.py resolves `frontend/dist` relative to `__file__`, so this layout matches)
COPY --from=frontend-builder /build/dist ./frontend/dist

# Run uvicorn from the backend directory; PORT is injected by Railway
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
