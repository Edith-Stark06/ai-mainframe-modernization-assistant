"""
Tests for :mod:`app.ai.providers.openai_compatible` and its ``nvidia`` wiring.

Purpose:
    Verify the OpenAI-compatible provider (used for NVIDIA NIM) maps requests
    and replies correctly -- including a reasoning model's separate
    ``reasoning_content`` -- and turns every failure into the provider-neutral
    error the platform already handles. The HTTP layer is replaced by
    ``httpx.MockTransport``; no network access and no real key is used.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.api.dependencies.ai import get_llm_provider
from app.core import config as cfg_mod

_BASE = "https://nim.example/v1"


def _reply(content="Hello.", finish="stop", reasoning="thinking...", **extra):
    return {
        "id": "x",
        "model": "served-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning,
                },
            }
        ],
        "usage": {"prompt_tokens": 9, "completion_tokens": 4},
        **extra,
    }


def _provider(handler, key="nvapi-test") -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        model="deepseek-ai/default",
        api_key=key,
        base_url=_BASE + "/",
        transport=httpx.MockTransport(handler),
    )


def _status(code: int, body=None):
    return lambda request: httpx.Response(code, json=body or {"detail": "boom"})


# ---------------------------------------------------------------------------
# Request / response mapping
# ---------------------------------------------------------------------------


def test_request_is_sent_to_chat_completions_with_bearer_auth() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_reply())

    _provider(handler).generate(
        LLMRequest(prompt="Explain.", temperature=0.3, max_tokens=500)
    )
    assert seen["url"] == f"{_BASE}/chat/completions"  # trailing slash tolerated
    assert seen["auth"] == "Bearer nvapi-test"
    assert seen["body"] == {
        "model": "deepseek-ai/default",
        "messages": [{"role": "user", "content": "Explain."}],
        "stream": False,
        "max_tokens": 500,
        "temperature": 0.3,
    }


def test_optional_fields_are_omitted_when_unset() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_reply())

    _provider(handler).generate(LLMRequest(prompt="hi"))
    assert "max_tokens" not in seen["body"]
    assert "temperature" not in seen["body"]


def test_request_model_overrides_the_default() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=_reply())

    _provider(handler).generate(LLMRequest(prompt="hi", model="other/model"))
    assert seen["model"] == "other/model"


def test_answer_is_content_not_the_reasoning_trace() -> None:
    result = _provider(lambda r: httpx.Response(200, json=_reply("pong"))).generate(
        LLMRequest(prompt="hi")
    )
    assert result.text == "pong"
    assert "thinking" not in result.text
    assert result.model == "served-model"
    assert result.usage == {"prompt_tokens": 9, "completion_tokens": 4}


def test_reply_without_usage_is_accepted() -> None:
    body = _reply()
    del body["usage"]
    result = _provider(lambda r: httpx.Response(200, json=body)).generate(
        LLMRequest(prompt="hi")
    )
    assert result.usage is None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410, 422])
def test_client_errors_are_configuration_errors(code: int) -> None:
    with pytest.raises(LLMConfigurationError):
        _provider(_status(code)).generate(LLMRequest(prompt="hi"))


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_rate_limit_and_server_errors_are_unavailable(code: int) -> None:
    with pytest.raises(LLMProviderUnavailableError):
        _provider(_status(code)).generate(LLMRequest(prompt="hi"))


def test_timeout_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMProviderUnavailableError, match="Timed out"):
        _provider(handler).generate(LLMRequest(prompt="hi"))


def test_connection_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(LLMProviderUnavailableError):
        _provider(handler).generate(LLMRequest(prompt="hi"))


def test_error_detail_is_surfaced_without_the_key() -> None:
    body = {"error": {"message": "model not found"}}
    with pytest.raises(LLMConfigurationError) as info:
        _provider(_status(404, body), key="nvapi-secret").generate(
            LLMRequest(prompt="hi")
        )
    assert "model not found" in str(info.value)
    assert "nvapi-secret" not in str(info.value)


def test_gateway_timeout_with_an_empty_body_still_says_what_happened() -> None:
    with pytest.raises(LLMProviderUnavailableError, match=r"\(504\): Gateway Timeout"):
        _provider(lambda r: httpx.Response(504, content=b"")).generate(
            LLMRequest(prompt="hi")
        )


def test_end_of_life_model_message_is_surfaced() -> None:
    body = {"title": "Gone", "status": 410, "detail": "reached its end of life"}
    with pytest.raises(LLMConfigurationError, match="end of life"):
        _provider(_status(410, body)).generate(LLMRequest(prompt="hi"))


def test_truncated_reasoning_with_no_answer_asks_for_more_tokens() -> None:
    body = _reply(content="", finish="length")
    with pytest.raises(LLMConfigurationError, match="max_tokens"):
        _provider(lambda r: httpx.Response(200, json=body)).generate(
            LLMRequest(prompt="hi", max_tokens=5)
        )


def test_empty_answer_is_unavailable_not_a_blank_success() -> None:
    body = _reply(content="   ")
    with pytest.raises(LLMProviderUnavailableError, match="empty"):
        _provider(lambda r: httpx.Response(200, json=body)).generate(
            LLMRequest(prompt="hi")
        )


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{}]}])
def test_malformed_reply_is_unavailable(body) -> None:
    with pytest.raises(LLMProviderUnavailableError):
        _provider(lambda r: httpx.Response(200, json=body)).generate(
            LLMRequest(prompt="hi")
        )


def test_non_json_reply_is_unavailable() -> None:
    with pytest.raises(LLMProviderUnavailableError):
        _provider(lambda r: httpx.Response(200, text="<html>")).generate(
            LLMRequest(prompt="hi")
        )


@pytest.mark.parametrize(("key", "url"), [("", _BASE), ("k", "")])
def test_key_and_base_url_are_required(key: str, url: str) -> None:
    with pytest.raises(LLMConfigurationError):
        OpenAICompatibleProvider(model="m", api_key=key, base_url=url)


# ---------------------------------------------------------------------------
# get_llm_provider wiring
# ---------------------------------------------------------------------------


def _configure(monkeypatch: pytest.MonkeyPatch, **values) -> None:
    defaults = {
        "llm_provider": "nvidia",
        "nvidia_api_key": None,
        "nvidia_model": "deepseek-ai/configured",
        "nvidia_base_url": _BASE,
        "nvidia_timeout_s": 42.0,
    }
    for name, value in {**defaults, **values}.items():
        monkeypatch.setattr(cfg_mod.settings, name, value)


def test_opt_in_with_key_returns_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, nvidia_api_key=SecretStr("nvapi-abc"))
    provider = get_llm_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "deepseek-ai/configured"
    assert provider.base_url == _BASE
    assert provider._client.timeout.read == 42.0  # noqa: SLF001


@pytest.mark.parametrize("blank", [None, SecretStr(""), SecretStr("  ")])
def test_opt_in_without_a_key_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, blank
) -> None:
    _configure(monkeypatch, nvidia_api_key=blank)
    assert get_llm_provider() is None


def test_a_key_alone_does_not_enable_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, llm_provider="none", nvidia_api_key=SecretStr("nvapi-abc"))
    assert get_llm_provider() is None


def test_settings_repr_hides_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, nvidia_api_key=SecretStr("nvapi-very-secret"))
    assert "nvapi-very-secret" not in repr(cfg_mod.settings)
