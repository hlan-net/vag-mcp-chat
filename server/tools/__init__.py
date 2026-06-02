"""Register all VW vehicle tools on the FastMCP instance."""

from fastmcp import FastMCP

from server.tools import battery, charging, climate, location, summary  # noqa: F401


def register_all(mcp: FastMCP) -> None:
    """Import side-effects wire each tool module's decorators to `mcp`."""
    # Tools self-register via @mcp.tool() in their module bodies.
    # This function exists so main.py has a single explicit call site.
    pass
