"""Fernet-encrypted disk store for VW OIDC tokens.

The access token and refresh token are stored encrypted at rest in
data/vw_token.enc. The raw tokens never appear in logs or unencrypted files.
"""

import json
import logging
from pathlib import Path

from cryptography.fernet import Fernet

from server.auth.vw_oidc import OIDCTokens, refresh_access_token
from server.settings import settings

logger = logging.getLogger(__name__)

_STORE_KEY = "vw_tokens"


class TokenStore:
    def __init__(self) -> None:
        self._path: Path = settings.token_store_path
        self._fernet = Fernet(settings.mcp_fernet_key.encode())

    def save(self, tokens: OIDCTokens) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "id_token": tokens.id_token,
                "expires_at": tokens.expires_at,
            }
        ).encode()
        self._path.write_bytes(self._fernet.encrypt(payload))
        logger.info("VW tokens saved to %s", self._path)

    def load_raw(self) -> OIDCTokens | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._fernet.decrypt(self._path.read_bytes()))
            return OIDCTokens(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                id_token=data.get("id_token"),
                expires_at=data["expires_at"],
            )
        except Exception:
            logger.exception("Failed to load VW tokens from %s", self._path)
            return None

    async def load(self) -> OIDCTokens | None:
        """Load tokens, auto-refreshing if the access token is near expiry."""
        tokens = self.load_raw()
        if tokens is None:
            return None
        if tokens.is_expired and tokens.refresh_token:
            logger.info("VW access token expired; refreshing...")
            try:
                tokens = await refresh_access_token(tokens.refresh_token)
                self.save(tokens)
            except Exception:
                logger.exception("Token refresh failed")
                return None
        return tokens

    def exists(self) -> bool:
        return self._path.exists()

    def delete(self) -> None:
        if self._path.exists():
            self._path.unlink()


token_store = TokenStore()
