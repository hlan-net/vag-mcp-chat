# Expose the FastMCP instance so tool modules can do:
#   from server import mcp_instance as mcp
from server.mcp_app import mcp as mcp_instance  # noqa: F401
