"""
Tests for :mod:`app.ai.providers.anthropic` and its wiring.

Purpose:
    Verify the hosted-Claude provider maps requests/responses correctly and
    turns every failure into the provider-neutral error the rest of the
    platform already handles -- against the real ``anthropic`` SDK, with the
    HTTP layer replaced by ``httpx2.MockTransport`` so no network or key is
    needed and nothing is faked above the wire.

Coverage:
    Request mapping, response mapping, error classification (bad key / bad
    model -> configuration, rate limit / overloaded / server / connection ->
    unavailable), credential requirements, and ``get_llm_provider`` opt-in.
"""

from __future__ import annotations

import json

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest
from app.api.dependencies.ai import get_llm_provider
from app.core import config as cfg_mod

_OK_BODY = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test-model",
    "content": [
        {"type": "text", "text": "Hello, "},
        {"type": "text", "text": "world."},
    ],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 11, "output_tokens": 7},
}


def _provider(handler, **kwargs) -> AnthropicProvider:
    """A real provider whose SDK client talks to *handler* instead of the net."""
    provider = AnthropicProvider(
        model="claude-default", api_key=kwargs.pop("api_key", "sk-test"), **kwargs
    )
    provider._client = anthropic.Anthropic(  # noqa: SLF001
        api_key="sk-test",
        base_url=kwargs.get("base_url") or "https://api.anthropic.com",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return provider


def _error(status: int, kind: str = "api_error"):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            json={"type": "error", "error": {"type": kind, "message": "boom"}},
        )

    return handler


# ---------------------------------------------------------------------------
# Request / response mapping
# ---------------------------------------------------------------------------


def test_request_is_mapped_to_the_messages_api() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_OK_BODY)

    provider = _provider(handler)
    provider.generate(LLMRequest(prompt="Explain.", temperature=0.2, max_tokens=99))

    assert seen["url"].endswith("/v1/messages")
    assert seen["key"] == "sk-test"
    assert seen["body"]["model"] == "claude-default"
    assert seen["body"]["max_tokens"] == 99
    # accepted but not sent: the Messages API takes no sampling parameters
    assert "temperature" not in seen["body"]
    assert seen["body"]["messages"] == [{"role": "user", "content": "Explain."}]


def test_defaults_are_applied_when_the_request_gives_none() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_OK_BODY)

    _provider(handler).generate(LLMRequest(prompt="hi"))
    assert seen["body"]["max_tokens"] == 2048  # the API requires one
    assert "temperature" not in seen["body"]


def test_request_model_overrides_the_default() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_OK_BODY)

    _provider(handler).generate(LLMRequest(prompt="hi", model="claude-other"))
    assert seen["body"]["model"] == "claude-other"


def test_response_text_blocks_are_joined_and_usage_mapped() -> None:
    response = _provider(lambda r: httpx2.Response(200, json=_OK_BODY)).generate(
        LLMRequest(prompt="hi")
    )
    assert response.text == "Hello, world."
    assert response.model == "claude-test-model"
    assert response.usage == {"prompt_tokens": 11, "completion_tokens": 7}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "authentication_error"),
        (403, "permission_error"),
        (404, "not_found_error"),
        (400, "invalid_request_error"),
    ],
)
def test_client_errors_are_configuration_errors(status: int, kind: str) -> None:
    with pytest.raises(LLMConfigurationError):
        _provider(_error(status, kind)).generate(LLMRequest(prompt="hi"))


@pytest.mark.parametrize("status", [429, 500, 503, 529])
def test_rate_limit_and_server_errors_are_unavailable(status: int) -> None:
    with pytest.raises(LLMProviderUnavailableError):
        _provider(_error(status)).generate(LLMRequest(prompt="hi"))


def test_connection_failure_is_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    with pytest.raises(LLMProviderUnavailableError):
        _provider(handler).generate(LLMRequest(prompt="hi"))


def test_error_messages_never_contain_the_credential() -> None:
    with pytest.raises(LLMConfigurationError) as info:
        _provider(_error(401, "authentication_error"), api_key="sk-secret").generate(
            LLMRequest(prompt="hi")
        )
    assert "sk-secret" not in str(info.value)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", [None, ""])
def test_no_credentials_is_a_configuration_error(key) -> None:
    with pytest.raises(LLMConfigurationError):
        AnthropicProvider(model="m", api_key=key, auth_token=key)


def test_auth_token_alone_is_accepted() -> None:
    assert AnthropicProvider(model="m", auth_token="tok").model == "m"


# ---------------------------------------------------------------------------
# get_llm_provider wiring
# ---------------------------------------------------------------------------


def _configure(monkeypatch: pytest.MonkeyPatch, **values) -> None:
    defaults = {
        "llm_provider": "anthropic",
        "anthropic_model": "claude-configured",
        "anthropic_api_key": None,
        "anthropic_auth_token": None,
        "anthropic_base_url": "",
    }
    for name, value in {**defaults, **values}.items():
        monkeypatch.setattr(cfg_mod.settings, name, value)


def test_opt_in_with_key_returns_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, anthropic_api_key=SecretStr("sk-abc"))
    provider = get_llm_provider()
    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-configured"


def test_opt_in_with_token_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(
        monkeypatch,
        anthropic_auth_token=SecretStr("tok"),
        anthropic_base_url="https://gateway.example",
    )
    provider = get_llm_provider()
    assert isinstance(provider, AnthropicProvider)
    assert str(provider._client.base_url).startswith(  # noqa: SLF001
        "https://gateway.example"
    )


@pytest.mark.parametrize("blank", [None, SecretStr(""), SecretStr("   ")])
def test_opt_in_without_credentials_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, blank
) -> None:
    _configure(monkeypatch, anthropic_api_key=blank, anthropic_auth_token=blank)
    assert get_llm_provider() is None


def test_credentials_alone_do_not_enable_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, llm_provider="none", anthropic_api_key=SecretStr("sk-abc"))
    assert get_llm_provider() is None


def test_settings_repr_hides_the_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, anthropic_api_key=SecretStr("sk-very-secret"))
    assert "sk-very-secret" not in repr(cfg_mod.settings)
