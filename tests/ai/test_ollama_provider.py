"""
Tests for :class:`~app.ai.providers.ollama.OllamaProvider`.

Purpose:
    Verify the real Ollama-backed LLM provider actually works against
    a real, running Ollama server -- not just that it constructs
    without error. Error-path tests (unreachable server, unknown
    model) run unconditionally since they need no real model pulled.
    The full end-to-end generation test is marked slow and requires
    a real Ollama server reachable at OLLAMA_TEST_HOST (default
    http://localhost:11434) with OLLAMA_TEST_MODEL pulled (default
    qwen2.5:0.5b, a small model chosen for fast CI/local runs).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest
from app.ai.providers.ollama import OllamaProvider
from tests.ollama_support import (
    OLLAMA_TEST_HOST as _TEST_HOST,
    OLLAMA_TEST_MODEL as _TEST_MODEL,
    requires_ollama_model,
    requires_ollama_server,
)


def test_unreachable_server_raises_provider_unavailable() -> None:
    provider = OllamaProvider(model="irrelevant", host="http://localhost:1")
    with pytest.raises(LLMProviderUnavailableError):
        provider.generate(LLMRequest(prompt="hi"))


def test_unreachable_server_error_message_names_host() -> None:
    provider = OllamaProvider(model="irrelevant", host="http://localhost:1")
    with pytest.raises(LLMProviderUnavailableError, match="localhost:1"):
        provider.generate(LLMRequest(prompt="hi"))


@pytest.mark.slow
@requires_ollama_server
def test_unknown_model_against_real_server_raises_configuration_error() -> None:
    """A 404 'model not found' from a real, reachable server is a
    configuration mistake (wrong model name), not an outage."""
    provider = OllamaProvider(
        model="this-model-definitely-does-not-exist:999b", host=_TEST_HOST
    )
    with pytest.raises(LLMConfigurationError, match="not found"):
        provider.generate(LLMRequest(prompt="hi"))


@pytest.mark.slow
@requires_ollama_model
def test_real_generation_against_real_ollama_server() -> None:
    """The actual point of this provider: a real prompt to a real,
    locally-running model produces a real, non-empty response."""
    provider = OllamaProvider(model=_TEST_MODEL, host=_TEST_HOST)
    response = provider.generate(
        LLMRequest(prompt="Reply with exactly the word: PONG", max_tokens=10)
    )
    assert response.text.strip()
    assert response.model is not None


@pytest.mark.slow
@requires_ollama_model
def test_real_generation_respects_max_tokens() -> None:
    provider = OllamaProvider(model=_TEST_MODEL, host=_TEST_HOST)
    response = provider.generate(
        LLMRequest(prompt="Count from 1 to 100.", max_tokens=5)
    )
    # A tight max_tokens on a real model must actually truncate --
    # proving options={"num_predict": ...} was really wired through,
    # not silently ignored.
    assert len(response.text.split()) < 50


@pytest.mark.slow
@requires_ollama_model
def test_real_generation_reports_usage() -> None:
    provider = OllamaProvider(model=_TEST_MODEL, host=_TEST_HOST)
    response = provider.generate(LLMRequest(prompt="Say hi.", max_tokens=10))
    assert response.usage is not None
    assert response.usage.get("completion_tokens", 0) > 0
