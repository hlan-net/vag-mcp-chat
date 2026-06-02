"""Pytest configuration.

Environment variables are set at module level (before any server imports
happen during test collection) so that pydantic-settings and Fernet
initialise without requiring a real .env file.
"""

import os

from cryptography.fernet import Fernet

# Must run before any server.* module is imported by the test collector.
_fernet_key = Fernet.generate_key().decode()
os.environ.setdefault("MCP_JWT_SECRET", "test-jwt-secret-32-bytes-xxxxxxxxx")
os.environ.setdefault("MCP_FERNET_KEY", _fernet_key)
os.environ.setdefault("MCP_BASE_URL", "http://localhost:8000")
os.environ.setdefault("VW_OIDC_CLIENT_ID", "test-client-id")
os.environ.setdefault("VW_OIDC_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
