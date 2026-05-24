# syntax=docker/dockerfile:1.24
# Multi-stage Dockerfile for Whoopster
# Stage 1: Builder - Install dependencies with uv on Chainguard Wolfi-based image
# Stage 2: Runtime - Chainguard distroless Python image

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM cgr.dev/chainguard/python:latest-dev AS builder

# uv ships at /usr/bin/uv in this Chainguard image; no separate copy needed.
USER root

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# =============================================================================
# Stage 2: Runtime (distroless)
# =============================================================================
FROM cgr.dev/chainguard/python:latest

LABEL maintainer="whoopster"
LABEL description="Whoop data collector and synchronization service"
LABEL version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --chown=nonroot:nonroot --from=builder /app/.venv /app/.venv
COPY --chown=nonroot:nonroot src/ /app/src/
COPY --chown=nonroot:nonroot scripts/ /app/scripts/
COPY --chown=nonroot:nonroot alembic.ini /app/

USER nonroot

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys; from src.config import settings; sys.exit(0)"]

ENTRYPOINT ["python", "/app/scripts/entrypoint.py"]
