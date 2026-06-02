"""MCP client with OAuth 2.1 + PKCE S256 authentication.

FastMCP's built-in `Client` with `auth=OAuth(...)` handles the full PKCE S256
flow automatically:
  - Discovers the authorization server from /.well-known/oauth-authorization-server
  - Generates code_verifier + code_challenge (S256)
  - Starts a local callback HTTP server on callback_port
  - Prompts the user to open the consent URL
  - Exchanges the authorization code for a short-lived FastMCP JWT
  - Transparently refreshes tokens when they expire

The agent never holds raw VW tokens — only the FastMCP-issued JWT.
"""

import logging
from typing import Any

from fastmcp import Client
from fastmcp.client.auth import OAuth

from server.settings import settings

logger = logging.getLogger(__name__)


class MCPClient:
    """Thin wrapper around FastMCP's Client, authenticated via OAuth 2.1 PKCE.

    Usage:
        async with MCPClient() as client:
            tools = await client.list_tools()
            result = await client.call_tool("get_vehicle_battery", {"vin": "WVW..."})
    """

    def __init__(
        self,
        server_url: str | None = None,
        callback_port: int | None = None,
    ) -> None:
        self._server_url = (server_url or settings.mcp_server_url).rstrip("/")
        self._callback_port = callback_port or settings.agent_callback_port
        self._oauth = OAuth(
            scopes=["vehicle:read"],
            callback_port=self._callback_port,
        )
        self._client: Client | None = None

    async def __aenter__(self) -> "MCPClient":
        mcp_url = f"{self._server_url}/mcp"
        self._client = Client(mcp_url, auth=self._oauth)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.__aexit__(*args)

    async def list_tools(self) -> list[dict]:
        """Return tool descriptors as plain dicts (compatible with OpenAI functions format)."""
        assert self._client is not None
        tools = await self._client.list_tools()
        result = []
        for tool in tools:
            # FastMCP's Tool has .name, .description, .inputSchema (camelCase from MCP spec)
            schema = (
                getattr(tool, "inputSchema", None)
                or getattr(tool, "input_schema", None)
                or {"type": "object", "properties": {}}
            )
            result.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": schema,
                }
            )
        return result

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Call an MCP tool and return its result as a Python object."""
        assert self._client is not None
        result = await self._client.call_tool(name, arguments)
        # FastMCP's CallToolResult: .data contains the deserialized value
        if result.data is not None:
            return result.data
        # Fallback: extract text from content blocks
        if result.content:
            import json
            text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
            try:
                return json.loads(text)
            except (json.JSONDecodeError, AttributeError):
                return text
        return None
