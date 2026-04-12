# ===========================================
# STAGE 1: Build dependencies
# ===========================================
FROM python:3.12-slim-bookworm AS builder

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy uv files
COPY pyproject.toml uv.lock ./

# Install dependencies into /opt/venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
# Use frozen lockfile, no dev dependencies
RUN uv sync --frozen --no-dev --no-install-project

# ===========================================
# STAGE 2: Runtime image
# ===========================================
FROM python:3.12-slim-bookworm AS runtime

# Metadata
LABEL maintainer="PAL MCP Server Team"
LABEL version="1.0.0"
LABEL description="PAL MCP Server - AI-powered Model Context Protocol server"
LABEL org.opencontainers.image.title="pal-mcp-server"
LABEL org.opencontainers.image.source="https://github.com/BeehiveInnovations/pal-mcp-server"
LABEL org.opencontainers.image.licenses="Apache 2.0 License"

# Create non-root user
RUN groupadd -r paluser && useradd -r -g paluser paluser

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application code
COPY --chown=paluser:paluser . .

# Create directories
RUN mkdir -p logs tmp && chown -R paluser:paluser logs tmp

# Healthcheck
COPY --chown=paluser:paluser docker/scripts/healthcheck.py /usr/local/bin/healthcheck.py
RUN chmod +x /usr/local/bin/healthcheck.py

USER paluser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python /usr/local/bin/healthcheck.py

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "server.py"]