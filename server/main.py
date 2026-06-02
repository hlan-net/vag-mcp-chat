"""MCP server entry point.

Run with:
    python -m server.main
    uvicorn server.main:app --host 0.0.0.0 --port 8000

The server exposes a Streamable-HTTP MCP endpoint at /mcp.
OAuth 2.1 + PKCE endpoints are handled by FastMCP's built-in OAuthProxy.

Before starting for the first time, authenticate your VW account:
    python -m server.setup
"""

import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Mount

from server.mcp_app import mcp
from server.settings import settings
from server.state import data_poller, token_store

# Tool modules self-register via @mcp.tool() when imported.
import server.tools.battery  # noqa: F401
import server.tools.charging  # noqa: F401
import server.tools.climate  # noqa: F401
import server.tools.location  # noqa: F401
import server.tools.summary  # noqa: F401

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Build FastMCP's underlying Starlette/ASGI app.
_mcp_asgi = mcp.http_app()


@asynccontextmanager
async def _lifespan(_app):
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    if not token_store.exists():
        logger.warning(
            "No VW tokens found. Run `python -m server.setup` to authenticate "
            "with your VW ID before vehicle data will be available."
        )
    else:
        data_poller.start()
        logger.info("Data poller started (VIN poll interval: %ds).", settings.vw_data_poll_interval_seconds)

    # Run FastMCP's own lifespan (initialises session manager, auth stores, etc.)
    async with _mcp_asgi.lifespan(_app):
        yield

    data_poller.stop()
    logger.info("Server shut down.")


# Wrap FastMCP in a Starlette app that owns the combined lifespan.
# All HTTP requests are forwarded to the FastMCP ASGI app.
app = Starlette(
    lifespan=_lifespan,
    routes=[Mount("/", app=_mcp_asgi)],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=False)
