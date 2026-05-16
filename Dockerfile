# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
# Multi-stage Dockerfile for Whoopster
# Stage 1: Builder - Install dependencies with uv
# Stage 2: Runtime - Minimal production image

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.14-slim@sha256:7a500125bc50693f2214e842a621440a1b1b9cbb2188f74ab045d29ed2ea5856 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11@sha256:1025398289b62de8269e70c45b91ffa37c373f38118d7da036fb8bb8efc85d97 /uv /uvx /usr/local/bin/

# Build deps (gcc/g++/libpq-dev) kept in case any wheel is unavailable on 3.14
# and uv falls back to building from sdist.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.14-slim@sha256:7a500125bc50693f2214e842a621440a1b1b9cbb2188f74ab045d29ed2ea5856

LABEL maintainer="whoopster"
LABEL description="Whoop data collector and synchronization service"
LABEL version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r whoopster && useradd -r -g whoopster whoopster

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY alembic.ini /app/

RUN mkdir -p /app/logs && chown -R whoopster:whoopster /app

USER whoopster

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; from src.config import settings; sys.exit(0)"

CMD ["sh", "-c", "/app/.venv/bin/alembic upgrade head && /app/.venv/bin/python -m src.main"]
