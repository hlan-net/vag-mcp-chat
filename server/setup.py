"""One-time VW EU Data Act authentication setup.

Run this before starting the MCP server to store your VW credentials:
    python -m server.setup

The script:
  1. Generates a VW OIDC authorization URL.
  2. Opens a temporary local web server on port 8001 to catch the callback.
  3. Exchanges the authorization code for VW tokens.
  4. Saves the encrypted tokens to data/vw_token.enc.

After setup completes, start the MCP server normally with `python -m server.main`.
"""

import asyncio
import secrets
import sys
import webbrowser
from urllib.parse import parse_qs, urlparse

from aiohttp import web  # type: ignore[import]  # lightweight one-off server

from server.auth.token_store import token_store
from server.auth.vw_oidc import build_authorize_url, exchange_code, generate_state
from server.settings import settings

_CALLBACK_PORT = 8001
_received: dict[str, str] = {}
_done = asyncio.Event()


async def _callback_handler(request: web.Request) -> web.Response:
    params = dict(request.query)
    _received.update(params)
    _done.set()
    return web.Response(
        text="<html><body><h2>Authentication complete!</h2>"
             "<p>You can close this tab and return to the terminal.</p></body></html>",
        content_type="text/html",
    )


async def _run_local_server() -> None:
    app = web.Application()
    app.router.add_get("/setup/callback", _callback_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", _CALLBACK_PORT)
    await site.start()
    print(f"Listening for VW callback on http://localhost:{_CALLBACK_PORT}/setup/callback")
    await _done.wait()
    await runner.cleanup()


async def main() -> None:
    state = generate_state()
    # For setup we use a dedicated callback, not the server's /auth/callback.
    # Override the callback URL temporarily for the setup flow.
    setup_callback = f"http://localhost:{_CALLBACK_PORT}/setup/callback"

    # Build the auth URL with the setup callback
    params = {
        "response_type": "code",
        "client_id": settings.vw_oidc_client_id,
        "redirect_uri": setup_callback,
        "scope": settings.vw_oidc_scopes,
        "state": state,
    }
    from urllib.parse import urlencode
    auth_url = f"{settings.vw_oidc_authorize_url}?{urlencode(params)}"

    print("\n── VW EU Data Act Setup ────────────────────────────────────────────────")
    print("Opening your browser to authenticate with your VW ID...\n")
    print(f"Auth URL:\n  {auth_url}\n")
    print("If the browser did not open automatically, copy the URL above.")

    webbrowser.open(auth_url)
    await _run_local_server()

    code = _received.get("code")
    returned_state = _received.get("state")

    if not code:
        print("\nError: No authorization code received. Did you cancel the login?")
        sys.exit(1)

    if returned_state != state:
        print("\nError: State mismatch — possible CSRF. Aborting.")
        sys.exit(1)

    print("\nExchanging authorization code for VW tokens...")
    tokens = await exchange_code(code, redirect_uri=setup_callback)
    token_store.save(tokens)
    print(f"✓ VW tokens saved to {settings.token_store_path}")
    print("\nSetup complete. Start the MCP server with:\n  python -m server.main\n")


if __name__ == "__main__":
    asyncio.run(main())
