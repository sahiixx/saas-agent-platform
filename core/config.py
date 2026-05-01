"""Central configuration with env-overridable settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── App ──
    app_name: str = "SaaS Agent Platform"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    allowed_origins: list[str] = ["*"]

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8080

    # ── Data ──
    data_dir: str = str(Path(__file__).parent.parent / "data")
    database_url: str = "sqlite:///./data/tenants.db"

    # ── Hermes — uses local Hermes Agent installation ──
    hermes_profile: str = "saas-tenant"
    hermes_config_dir: str = "~/.hermes/profiles"

    # ── Bus ──
    bus_url: str = "http://127.0.0.1:8090"

    # ── MCP ──
    mcp_default_servers: list[str] = [
        "filesystem",
        "github",
        "postgres",
    ]

    # ── Ollama (for local model fallback) ──
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "kimi-k2.6:cloud"


settings = Settings()
