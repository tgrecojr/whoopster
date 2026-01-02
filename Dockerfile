# Multi-stage Dockerfile for Whoopster
# Stage 1: Builder - Install dependencies and compile
# Stage 2: Runtime - Minimal production image

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM python:3.14-slim@sha256:3955a7dd66ccf92b68d0232f7f86d892eaf75255511dc7e98961bdc990dc6c9b as builder

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install Python dependencies to /install
RUN pip install --no-cache-dir --prefix=/install --no-warn-script-location \
    -r requirements.txt

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.14-slim@sha256:3955a7dd66ccf92b68d0232f7f86d892eaf75255511dc7e98961bdc990dc6c9b

# Metadata
LABEL maintainer="whoopster"
LABEL description="Whoop data collector and synchronization service"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    # Prevent pip from checking for updates
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r whoopster && useradd -r -g whoopster whoopster

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY alembic.ini /app/

# Create directories for logs and data
RUN mkdir -p /app/logs && chown -R whoopster:whoopster /app

# Switch to non-root user
USER whoopster

# Health check - simple Python import test
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; from src.config import settings; sys.exit(0)"

# Run database migrations and start application
CMD ["sh", "-c", "alembic upgrade head && python -m src.main"]
