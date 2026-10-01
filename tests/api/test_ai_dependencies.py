"""
Tests for :mod:`app.api.dependencies.ai`.

Purpose:
    Verify get_llm_provider() defaults to None (no provider configured
    -- must never silently assume a model is available), returns a real
    provider only when explicitly opted into via settings.llm_provider
    ("nvidia" or "anthropic", each with its credential), does not cache a
    stale answer across a settings change, and treats any other value
    (including the removed "ollama") as not configured.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.api.dependencies.ai import get_ai_orchestrator, get_llm_provider
from app.core import config as cfg_mod


def test_default_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "none")
    assert get_llm_provider() is None


def test_nvidia_opt_in_returns_the_openai_compatible_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "nvidia")
    monkeypatch.setattr(cfg_mod.settings, "nvidia_api_key", SecretStr("k"))
    monkeypatch.setattr(cfg_mod.settings, "nvidia_model", "some/model")
    monkeypatch.setattr(cfg_mod.settings, "nvidia_base_url", "https://example/v1")

    provider = get_llm_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "some/model"
    assert provider.base_url == "https://example/v1"


@pytest.mark.parametrize("removed_or_unknown", ["ollama", "OLLAMA", "unknown", ""])
def test_any_other_provider_name_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, removed_or_unknown: str
) -> None:
    """``ollama`` used to be a provider; it must now simply be unconfigured,
    never an error and never a silent fallback to another provider."""
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", removed_or_unknown)
    monkeypatch.setattr(cfg_mod.settings, "nvidia_api_key", SecretStr("k"))
    monkeypatch.setattr(cfg_mod.settings, "anthropic_api_key", SecretStr("k"))
    assert get_llm_provider() is None


def test_toggling_setting_is_reflected_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: get_llm_provider must not cache a stale
    answer across a settings change (it originally did, via an
    unnecessary lru_cache -- constructing a provider is cheap, unlike the
    real embedding model load get_embedding_provider caches for a
    genuine reason)."""
    monkeypatch.setattr(cfg_mod.settings, "nvidia_api_key", SecretStr("k"))
    monkeypatch.setattr(cfg_mod.settings, "anthropic_api_key", SecretStr("k"))

    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "none")
    assert get_llm_provider() is None

    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "nvidia")
    assert isinstance(get_llm_provider(), OpenAICompatibleProvider)

    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "anthropic")
    assert isinstance(get_llm_provider(), AnthropicProvider)

    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "none")
    assert get_llm_provider() is None


def test_get_ai_orchestrator_is_none_when_provider_is_none() -> None:
    assert get_ai_orchestrator(provider=None) is None


def test_get_ai_orchestrator_wires_the_provider_into_both_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "nvidia")
    monkeypatch.setattr(cfg_mod.settings, "nvidia_api_key", SecretStr("k"))
    provider = get_llm_provider()

    orchestrator = get_ai_orchestrator(provider=provider)
    assert orchestrator is not None
    assert orchestrator._explanation_service._provider is provider
    assert orchestrator._documentation_service._provider is provider
