"""Runtime configuration, environment-driven with sane local defaults."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTLAB_", env_file=".env", extra="ignore")

    # SQLite needs zero services for bare-metal dev and tests;
    # docker-compose overrides this with a PostgreSQL URL.
    database_url: str = "sqlite:///./agentlab.db"

    # Comma-separated. Empty = open local mode (no auth on the write path).
    api_keys: str = ""

    # Comma-separated CORS origins for the dashboard dev server.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    environment: str = "development"

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
