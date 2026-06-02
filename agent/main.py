"""CLI entry point for the VW Vehicle Agent.

Usage:
    python -m agent.main
    python -m agent.main --vin WVWZZZ1JZYW123456
    python -m agent.main --server http://localhost:8000
"""

import argparse
import asyncio
import logging

from agent.chat import ChatAgent
from agent.mcp_client import MCPClient
from server.settings import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VW Vehicle Agent CLI")
    parser.add_argument(
        "--server",
        default=settings.mcp_server_url,
        help="MCP server URL (default: %(default)s)",
    )
    parser.add_argument(
        "--vin",
        default=settings.vw_default_vin,
        help="Default VIN to query (overrides VW_DEFAULT_VIN env var)",
    )
    parser.add_argument(
        "--callback-port",
        type=int,
        default=settings.agent_callback_port,
        help="Local port for OAuth redirect (default: %(default)s)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    # Override default VIN from CLI arg
    if args.vin:
        settings.vw_default_vin = args.vin

    async with MCPClient(args.server, callback_port=args.callback_port) as mcp:
        agent = ChatAgent(mcp)
        await agent.initialize()
        await agent.run_loop()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
