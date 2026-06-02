# syntax=docker/dockerfile:1
# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

COPY pyproject.toml .
COPY server/ server/
COPY agent/ agent/

# Install all dependencies into /build/.venv
RUN uv venv .venv && \
    uv pip install --python .venv/bin/python -e "."

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/hlan-net/vag-mcp-chat"
LABEL org.opencontainers.image.description="VW Vehicle MCP Agent Server"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy virtual environment and source from builder
COPY --from=builder /build/.venv .venv
COPY --from=builder /build/server server/
COPY --from=builder /build/agent agent/
COPY --from=builder /build/pyproject.toml .

# Create non-root user and data directory for encrypted token storage
RUN useradd --uid 1001 --no-create-home --shell /bin/false appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Health check against FastMCP's protected resource metadata endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/.well-known/oauth-protected-resource')" || exit 1

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
