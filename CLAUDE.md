# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (requires uv)
uv pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_parser.py -v

# Run a single test
pytest tests/test_parser.py::TestParseZip::test_parses_vehicle_json -v

# First-time VW account setup (stores encrypted tokens in data/vw_token.enc)
python -m server.setup

# Start the MCP + web chat server
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Run the CLI chat agent (connects to running server)
python -m agent.main --debug
python -m agent.main --server http://localhost:8000 --vin WVWXXX...
```

## Architecture

### Two-component system

**Server** (`server/`) — FastMCP 3.3.1 server that acts as both OAuth 2.1 Authorization Server and Resource Server. Deployed in k8s at `vag-chat.k3s.hlan.net`.

**Agent** (`agent/`) — CLI client that connects to the server via MCP protocol using FastMCP's built-in OAuth 2.1 + PKCE S256 client. Not deployed — runs locally.

### Request flows

**Web chat** (`GET /` → `POST /api/chat`): Browser → Starlette routes → `server/web/chat.py` → OpenAI API (streaming SSE) → tool functions called directly as Python (no MCP protocol round-trip). Session history lives in-memory.

**MCP protocol** (`/mcp`): External MCP clients (Claude Desktop, CLI agent) → FastMCP OAuth proxy → tool functions. Requires VW OIDC auth via the OAuthProxy.

**VW data flow**: `DataPoller` asyncio task (14-min interval) → `VWDataActClient` → EU Data Act portal → ZIP file → `parse_zip()` → `VehicleState` in-memory cache → tools read from cache.

### Critical import ordering

`server/__init__.py` exports `mcp_instance` from `server/mcp_app.py`. All five tool modules (`server/tools/*.py`) import `from server import mcp_instance as mcp` and self-register via `@mcp.tool()` at import time. `server/main.py` triggers this by importing the tool modules explicitly. **Do not import tool modules before `server/mcp_app.py` is initialised.**

Tools access shared state via `from server import state` (module reference, not direct import) so that `patch("server.state.data_poller", mock)` works correctly in tests.

### Settings

`server/settings.py` — pydantic-settings, reads from `.env`. Required fields with no defaults: `MCP_JWT_SECRET`, `MCP_FERNET_KEY`, `VW_OIDC_CLIENT_ID`, `VW_OIDC_CLIENT_SECRET`. `OPENAI_API_KEY` is optional (empty default) because the server itself doesn't call OpenAI — only `server/web/chat.py` does.

`conftest.py` sets all required env vars at module level before any server imports during test collection. Tests do not need a `.env` file.

### VW data source

Standard VW mobile endpoints return HTTP 401 (cryptographic attestation). All vehicle data comes from the EU Data Act portal (`eu-data-act.drivesomethinggreater.com`), which delivers telemetry as a ZIP file within 15 minutes of a request. The ZIP's internal field names are not publicly documented — `server/vw/parser.py` uses a candidate name mapping; run with `DEBUG` logging to discover actual field names from a real ZIP.

### Docker / k8s

The Dockerfile builds the venv at `/app/.venv` in the builder stage (not `/build`) so that absolute shebang paths survive the multi-stage copy. CMD uses `python -m uvicorn` rather than the `uvicorn` script to avoid shebang issues entirely.

The GHCR package (`ghcr.io/hlan-net/vag-mcp-chat`) is **private** — the k8s namespace uses the `ghcr-pull-secret` imagePullSecret. To deploy a new version: push to `master`, CI builds and pushes `:master` + `:sha-<hash>`, then `helm upgrade` with the new SHA tag (avoid `:master` in Helm — the node caches it and `IfNotPresent` won't pull updates).

Helm release: `vag-mcp-chat` in namespace `vag-mcp-chat`. Upgrade:
```bash
helm upgrade vag-mcp-chat ./helm/vag-mcp-chat --namespace vag-mcp-chat --reuse-values --set image.tag=sha-<hash>
```
