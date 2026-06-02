"""VW EU Data Act OIDC helpers.

Handles building the authorization URL and exchanging the authorization code
for tokens server-side (the client never sees the raw VW tokens).

NOTE: The exact OIDC endpoint paths may need adjustment once verified against
the live portal's /.well-known/openid-configuration discovery document.
"""

import secrets
import time
from dataclasses import dataclass

import httpx

from server.settings import settings


@dataclass
class OIDCTokens:
    access_token: str
    refresh_token: str
    id_token: str | None
    expires_at: float  # Unix timestamp

    @property
    def is_expired(self) -> bool:
        return time.time() >= (self.expires_at - 60)


def build_authorize_url(state: str, code_challenge: str | None = None) -> str:
    """Build the VW OIDC authorization URL to redirect the user's browser to."""
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": settings.vw_oidc_client_id,
        "redirect_uri": settings.vw_callback_url,
        "scope": settings.vw_oidc_scopes,
        "state": state,
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{settings.vw_oidc_authorize_url}?{query}"


async def exchange_code(
    code: str,
    code_verifier: str | None = None,
    redirect_uri: str | None = None,
) -> OIDCTokens:
    """Exchange an authorization code for VW OIDC tokens (server-side only)."""
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri or settings.vw_callback_url,
        "client_id": settings.vw_oidc_client_id,
        "client_secret": settings.vw_oidc_client_secret,
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier

    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.vw_oidc_token_url, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    return OIDCTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        id_token=data.get("id_token"),
        expires_at=time.time() + data.get("expires_in", 3600),
    )


async def refresh_access_token(refresh_token: str) -> OIDCTokens:
    """Refresh a VW access token using the stored refresh token."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.vw_oidc_client_id,
        "client_secret": settings.vw_oidc_client_secret,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(settings.vw_oidc_token_url, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    return OIDCTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", refresh_token),
        id_token=data.get("id_token"),
        expires_at=time.time() + data.get("expires_in", 3600),
    )


def generate_state() -> str:
    return secrets.token_urlsafe(32)
