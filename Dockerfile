# syntax=docker/dockerfile:1.24@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# Multi-stage Dockerfile for Whoopster
# Stage 1: Builder - Install dependencies with uv
# Stage 2: Runtime - Minimal production image

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.14-slim@sha256:a7185a8e40af01bf891414a4df16ef10fc6000cee460a404a13da9029fe41604 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11@sha256:e590846f4776907b254ac0f44b5b380347af5d90d668138ca7938d1b0c2f98d3 /uv /uvx /usr/local/bin/

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
FROM python:3.14-slim@sha256:a7185a8e40af01bf891414a4df16ef10fc6000cee460a404a13da9029fe41604

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
