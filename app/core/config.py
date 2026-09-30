"""
Application Configuration

Loads environment variables using Pydantic Settings.

Author:
Edith Stark

Project:
AI-Powered Mainframe Modernization Assistant
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown variables in .env
    )

    # ==========================
    # Application
    # ==========================

    app_name: str = "AI Mainframe Modernization Assistant"
    app_version: str = "0.1.0"

    # ==========================
    # Server
    # ==========================

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:3000",
    ]

    # ==========================
    # Logging
    # ==========================

    log_level: str = "INFO"

    # ==========================
    # Workspace
    # ==========================

    workspace_dir: str = "workspace"

    max_upload_mb: int = 20

    # ==========================
    # AI
    # ==========================

    #: "none" (default -- no LLM configured, matching every existing
    #: "provider not configured" test/behavior), "ollama" (a real,
    #: locally-hosted Ollama server) or "anthropic" (hosted Claude models;
    #: see app.api.dependencies.ai.get_llm_provider). Never assumed on: an
    #: operator must explicitly opt in.
    llm_provider: str = "none"
    ollama_model: str = "llama3"
    ollama_host: str = "http://localhost:11434"

    #: Hosted Claude models, selected with ``LLM_PROVIDER=anthropic``. The
    #: credentials come only from the environment (or an untracked ``.env``)
    #: and are held as ``SecretStr`` so they never appear in a repr or log.
    #: Give an API key, or a bearer token for a gateway; blank values count
    #: as unset. ``ANTHROPIC_BASE_URL`` points at a proxy/gateway instead of
    #: Anthropic's own endpoint.
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_api_key: SecretStr | None = None
    anthropic_auth_token: SecretStr | None = None
    anthropic_base_url: str = ""

    #: Load the embedding model in a background thread at startup, so
    #: the first /chat or /chat/index request does not pay the
    #: torch-import + model-load cost (about a minute in a fresh
    #: container -- longer than the Streamlit client's 30s timeout).
    #: Off by default: tests and local development should not each pay a
    #: real model load just to start the app.
    warm_embeddings: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


settings = get_settings()
