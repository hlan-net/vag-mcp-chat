"""FastMCP application instance.

Kept in its own module so tool files can import `mcp` without circular
dependencies (server/main.py imports tools, tools import mcp_app).
"""

from fastmcp import FastMCP
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier

from server.settings import settings

# FastMCP acts as both OAuth AS (toward MCP clients) and RS (tool enforcement).
# VW OIDC is the upstream identity provider: the user authenticates once with
# their VW ID and FastMCP issues a short-lived JWT to the agent.
# The raw VW upstream tokens are stored server-side (see server/auth/token_store.py).

_token_verifier = JWTVerifier(
    jwks_uri=f"{settings.mcp_base_url}/oauth/jwks",
    issuer=settings.mcp_base_url,
    # FastMCP uses the client_id (VW app's client_id) as the JWT audience.
    audience=settings.vw_oidc_client_id,
)

_auth = OAuthProxy(
    upstream_authorization_endpoint=settings.vw_oidc_authorize_url,
    upstream_token_endpoint=settings.vw_oidc_token_url,
    upstream_client_id=settings.vw_oidc_client_id,
    upstream_client_secret=settings.vw_oidc_client_secret,
    base_url=settings.mcp_base_url,
    jwt_signing_key=settings.mcp_jwt_secret,
    token_verifier=_token_verifier,
)

mcp = FastMCP("VW Vehicle Agent", auth=_auth)
