"""
Application Configuration

Loads environment variables using Pydantic Settings.

Author:
Edith Stark

Project:
AI-Powered Mainframe Modernization Assistant
"""

from functools import lru_cache

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
    #: "provider not configured" test/behavior) or "ollama" (use a
    #: real, locally-hosted Ollama server as the production LLM
    #: provider; see app.api.dependencies.ai.get_llm_provider). Never
    #: assumed on: an operator must explicitly opt in, since Ollama may
    #: not be installed/running in every deployment.
    llm_provider: str = "none"
    ollama_model: str = "llama3"
    ollama_host: str = "http://localhost:11434"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


settings = get_settings()
