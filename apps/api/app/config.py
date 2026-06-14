"""Runtime configuration, environment-driven with sane local defaults."""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTLAB_", env_file=".env", extra="ignore", populate_by_name=True
    )

    # SQLite needs zero services for bare-metal dev and tests;
    # docker-compose overrides this with a PostgreSQL URL.
    database_url: str = "sqlite:///./agentlab.db"

    # Comma-separated. Empty = open local mode (no auth on the write path).
    api_keys: str = ""

    # Comma-separated CORS origins for the dashboard dev server.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    environment: str = "development"

    # ---- Model gateway BYOK (v0.7) ----
    # Read from the conventional unprefixed env vars (OPENAI_API_KEY, …) only;
    # never stored in the DB, returned to clients, or logged. The mock provider
    # needs none of these.
    openai_api_key: str = Field(
        default="", validation_alias=AliasChoices("OPENAI_API_KEY", "AGENTLAB_OPENAI_API_KEY")
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "AGENTLAB_OPENAI_BASE_URL"),
    )
    anthropic_api_key: str = Field(
        default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AGENTLAB_ANTHROPIC_API_KEY")
    )
    # GEMINI_API_KEY is preferred over GOOGLE_API_KEY when both are set
    # (AliasChoices resolves left-to-right).
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GEMINI_API_KEY", "GOOGLE_API_KEY", "AGENTLAB_GEMINI_API_KEY"
        ),
    )
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        validation_alias=AliasChoices("GEMINI_BASE_URL", "AGENTLAB_GEMINI_BASE_URL"),
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "AGENTLAB_OLLAMA_BASE_URL"),
    )
    # Local models are slow: a 7B coder model (e.g. qwen2.5-coder, the runtime
    # template default) generating a full page can take minutes. Per-completion
    # timeout for the Ollama provider only; raise it for bigger models/pages.
    ollama_timeout_seconds: float = Field(
        default=600.0,
        validation_alias=AliasChoices("OLLAMA_TIMEOUT_SECONDS", "AGENTLAB_OLLAMA_TIMEOUT_SECONDS"),
    )
    openrouter_api_key: str = Field(
        default="", validation_alias=AliasChoices("OPENROUTER_API_KEY", "AGENTLAB_OPENROUTER_API_KEY")
    )
    # Local-first provider secrets configured through the UI (v0.9.1).
    # Gitignored JSON file, chmod 0600; values overlay the env vars above.
    secrets_file: str = ".agentlab-secrets.json"

    # ---- Runtime workspace sandbox (v1.2) ----
    # Root for workspace-bounded file sandboxes; every file operation is
    # confined beneath {workspaces_root}/{workspace_id}. Gitignored.
    workspaces_root: str = ".agentlab-workspaces"

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
