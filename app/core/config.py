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

    ollama_model: str = "llama3"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


settings = get_settings()
