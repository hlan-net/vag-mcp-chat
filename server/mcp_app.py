"""FastMCP application instance.

Kept in its own module so tool files can import `mcp` without circular
dependencies (server/main.py imports tools, tools import mcp_app).
"""

import hashlib
from pathlib import Path

from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier
from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from server.settings import settings

# FastMCP acts as both OAuth AS (toward MCP clients) and RS (tool enforcement).
# VW OIDC is the upstream identity provider: the user authenticates once with
# their VW ID and FastMCP issues a short-lived JWT to the agent.
# The raw VW upstream tokens are stored server-side (see server/auth/token_store.py).

_token_verifier = JWTVerifier(
    # OAuthProxy signs with jwt_signing_key using HS256.
    # For HS256 the "public key" is the same shared secret.
    # No audience restriction — DCR clients have dynamic IDs.
    public_key=settings.mcp_jwt_secret,
    algorithm="HS256",
    issuer=settings.mcp_base_url,
)

# Build an explicit client_storage so FastMCP writes to /app/data/oauth
# instead of defaulting to ~/.fastmcp (which doesn't exist in the container
# because the runtime user was created with --no-create-home).
_storage_key = hashlib.sha256(settings.mcp_jwt_secret.encode()).digest()[:32]
_fernet_key = Fernet.generate_key()  # ephemeral per process; tokens refresh via upstream
_oauth_storage_dir = Path(settings.data_dir) / "oauth"
_oauth_storage_dir.mkdir(parents=True, exist_ok=True)

_client_storage = FernetEncryptionWrapper(
    key_value=FileTreeStore(data_directory=_oauth_storage_dir),
    fernet=Fernet(key=_fernet_key),
)

_auth = OAuthProxy(
    upstream_authorization_endpoint=settings.vw_oidc_authorize_url,
    upstream_token_endpoint=settings.vw_oidc_token_url,
    upstream_client_id=settings.vw_oidc_client_id,
    upstream_client_secret=settings.vw_oidc_client_secret,
    base_url=settings.mcp_base_url,
    jwt_signing_key=settings.mcp_jwt_secret,
    token_verifier=_token_verifier,
    client_storage=_client_storage,
)

mcp = FastMCP("VW Vehicle Agent", auth=_auth)
