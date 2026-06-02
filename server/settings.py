from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MCP server
    mcp_jwt_secret: str
    mcp_fernet_key: str
    mcp_base_url: str = "http://localhost:8000"

    # VW EU Data Act OIDC
    vw_oidc_issuer: str = "https://eu-data-act.drivesomethinggreater.com"
    vw_oidc_client_id: str
    vw_oidc_client_secret: str
    vw_oidc_scopes: str = "openid profile email vehicle:read"

    # Vehicle
    vw_default_vin: str = ""

    # Polling
    vw_data_poll_interval_seconds: int = 840

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o"

    # Agent
    mcp_server_url: str = "http://localhost:8000"
    agent_callback_port: int = 9000

    # Storage path for encrypted VW tokens
    data_dir: Path = Path("data")

    @property
    def token_store_path(self) -> Path:
        return self.data_dir / "vw_token.enc"

    @property
    def vw_oidc_authorize_url(self) -> str:
        return f"{self.vw_oidc_issuer}/oauth/authorize"

    @property
    def vw_oidc_token_url(self) -> str:
        return f"{self.vw_oidc_issuer}/oauth/token"

    @property
    def vw_callback_url(self) -> str:
        return f"{self.mcp_base_url}/auth/callback"


settings = Settings()
