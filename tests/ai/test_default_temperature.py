"""Default temperature for providers that accept one."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.ai.providers.models import LLMRequest
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.api.dependencies.ai import get_llm_provider
from app.core import config as cfg_mod


def _nim(default: float | None, seen: dict) -> OpenAICompatibleProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )

    return OpenAICompatibleProvider(
        model="m",
        api_key="k",
        base_url="https://x/v1",
        transport=httpx.MockTransport(handler),
        default_temperature=default,
    )


def test_openai_compatible_sends_the_default_when_request_has_none() -> None:
    seen: dict = {}
    _nim(0.0, seen).generate(LLMRequest(prompt="hi"))
    assert seen["body"]["temperature"] == 0.0


def test_request_temperature_overrides_the_default() -> None:
    seen: dict = {}
    _nim(0.0, seen).generate(LLMRequest(prompt="hi", temperature=0.7))
    assert seen["body"]["temperature"] == 0.7


def test_no_default_and_no_request_temperature_sends_none() -> None:
    seen: dict = {}
    _nim(None, seen).generate(LLMRequest(prompt="hi"))
    assert "temperature" not in seen["body"]


class _FakeOllamaClient:
    def __init__(self) -> None:
        self.options: dict | None = None

    def generate(self, *, model, prompt, options, stream):
        self.options = options
        return SimpleNamespace(
            response="ok", model=model, prompt_eval_count=1, eval_count=1
        )


def _ollama(default: float | None) -> tuple[OllamaProvider, _FakeOllamaClient]:
    provider = OllamaProvider(model="m", default_temperature=default)
    client = _FakeOllamaClient()
    provider._client = client  # type: ignore[assignment]  # noqa: SLF001
    return provider, client


def test_ollama_sends_the_default_temperature() -> None:
    provider, client = _ollama(0.0)
    provider.generate(LLMRequest(prompt="hi"))
    assert client.options == {"temperature": 0.0}


def test_ollama_request_temperature_wins() -> None:
    provider, client = _ollama(0.0)
    provider.generate(LLMRequest(prompt="hi", temperature=0.9, max_tokens=50))
    assert client.options == {"temperature": 0.9, "num_predict": 50}


def test_ollama_without_any_temperature_sends_no_options() -> None:
    provider, client = _ollama(None)
    provider.generate(LLMRequest(prompt="hi"))
    assert client.options is None


def test_settings_default_is_zero() -> None:
    assert cfg_mod.Settings.model_fields["llm_temperature"].default == 0.0


def test_get_llm_provider_applies_the_configured_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "nvidia")
    monkeypatch.setattr(cfg_mod.settings, "nvidia_api_key", SecretStr("k"))
    monkeypatch.setattr(cfg_mod.settings, "llm_temperature", 0.25)
    provider = get_llm_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider._default_temperature == 0.25  # noqa: SLF001

    monkeypatch.setattr(cfg_mod.settings, "llm_provider", "ollama")
    ollama = get_llm_provider()
    assert isinstance(ollama, OllamaProvider)
    assert ollama._default_temperature == 0.25  # noqa: SLF001
