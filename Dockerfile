# syntax=docker/dockerfile:1
# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Build directly at /app so venv shebang paths match the runtime location
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
COPY server/ server/
COPY agent/ agent/

# Install all dependencies into /app/.venv
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python -e "."

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/hlan-net/vag-mcp-chat"
LABEL org.opencontainers.image.description="VW Vehicle MCP Agent Server"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy virtual environment and source from builder (paths match — both /app)
COPY --from=builder /app/.venv .venv
COPY --from=builder /app/server server/
COPY --from=builder /app/agent agent/
COPY --from=builder /app/pyproject.toml .

# Create non-root user and data directory for encrypted token storage
RUN useradd --uid 1001 --no-create-home --shell /bin/false appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Health check against FastMCP's protected resource metadata endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/.well-known/oauth-authorization-server')" || exit 1

# Use python -m uvicorn to avoid relying on the script's shebang line
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
