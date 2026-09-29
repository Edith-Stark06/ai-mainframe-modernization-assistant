"""
Tests for :mod:`app.api.dependencies.ai`.

Purpose:
    Verify get_llm_provider() defaults to None (no provider configured
    -- must never silently assume Ollama is installed/running) and
    only returns a real OllamaProvider when explicitly opted into via
    settings.llm_provider == "ollama". A slow test proves the opted-in
    path actually produces a working provider against the real,
    locally-running Ollama server this environment has set up.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import os

import pytest

from app.api.dependencies.ai import get_ai_orchestrator, get_llm_provider
from app.ai.providers.ollama import OllamaProvider
from app.core import config as cfg_mod

_TEST_MODEL = os.environ.get("OLLAMA_TEST_MODEL", "qwen2.5:0.5b")
_TEST_HOST = os.environ.get("OLLAMA_TEST_HOST", "http://localhost:11434")


def test_default_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "none")
    assert get_llm_provider() is None


def test_ollama_opt_in_returns_ollama_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "ollama")
    monkeypatch.setattr(cfg_mod.settings, "ollama_model", "some-model")
    monkeypatch.setattr(cfg_mod.settings, "ollama_host", "http://example:1234")

    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "some-model"
    assert provider.host == "http://example:1234"


def test_toggling_setting_is_reflected_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: get_llm_provider must not cache a stale
    answer across a settings change (it originally did, via an
    unnecessary lru_cache -- constructing an OllamaProvider is cheap,
    unlike the real embedding model load get_embedding_provider caches
    for a genuine reason)."""
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "none")
    assert get_llm_provider() is None

    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "ollama")
    assert isinstance(get_llm_provider(), OllamaProvider)

    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "none")
    assert get_llm_provider() is None


def test_get_ai_orchestrator_is_none_when_provider_is_none() -> None:
    assert get_ai_orchestrator(provider=None) is None


@pytest.mark.slow
def test_ollama_provider_end_to_end_via_ai_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real point: opting in wires a real OllamaProvider all the
    way through to the orchestrator's services, and that provider can
    actually generate real text via the real, locally-running Ollama
    server -- not just a correctly-typed object. Whether a tiny model's
    raw output happens to match CodeExplanationService's structured
    "Summary:/Explanation:" parsing format is that service's own,
    separately-tested concern (tests/ai/test_explanation.py, with
    fakes) -- this test only verifies the dependency wiring and real
    generation, at the provider level already thoroughly covered by
    tests/ai/test_ollama_provider.py."""
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "ollama")
    monkeypatch.setattr(cfg_mod.settings, "ollama_model", _TEST_MODEL)
    monkeypatch.setattr(cfg_mod.settings, "ollama_host", _TEST_HOST)

    provider = get_llm_provider()
    orchestrator = get_ai_orchestrator(provider=provider)
    assert orchestrator is not None
    assert orchestrator._explanation_service._provider is provider
    assert orchestrator._documentation_service._provider is provider

    from app.ai.providers.models import LLMRequest

    assert provider is not None
    response = provider.generate(LLMRequest(prompt="Say hi.", max_tokens=10))
    assert response.text.strip()
