"""
OpenAI-compatible LLM Provider (NVIDIA NIM and similar).

Purpose:
    A real, hosted :class:`~app.ai.providers.base.LLMProvider` for any service
    that speaks the OpenAI ``/chat/completions`` protocol -- in particular
    NVIDIA NIM (``https://integrate.api.nvidia.com/v1``), which hosts models
    such as ``deepseek-ai/deepseek-v4.1-flash``. It uses ``httpx`` directly
    (already a project dependency), so no vendor SDK is added.

Responsibilities:
    - :class:`OpenAICompatibleProvider` -- translates a provider-agnostic
      :class:`~app.ai.providers.models.LLMRequest` into a chat-completions
      call and back into an :class:`~app.ai.providers.models.LLMResponse`,
      raising the provider-neutral error for a bad key/model/request
      (:class:`~app.ai.providers.errors.LLMConfigurationError`) versus a
      timeout, rate limit, network, or server failure
      (:class:`~app.ai.providers.errors.LLMProviderUnavailableError`).

Non-responsibilities:
    - Storing credentials: the key is passed in by the caller and is never
      logged or put in an error message.
    - Streaming: ``stream`` is always ``false``.
    - Reasoning traces: reasoning models return their chain of thought in a
      separate ``reasoning_content`` field; only the final ``content`` is
      returned as the answer.

Dependencies:
    - httpx

Examples:
    ::

        provider = OpenAICompatibleProvider(
            model="deepseek-ai/deepseek-v4.1-flash",
            api_key="nvapi-...",
            base_url="https://integrate.api.nvidia.com/v1",
        )
        response = provider.generate(LLMRequest(prompt="Say hello."))

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest, LLMResponse

__all__ = ["OpenAICompatibleProvider"]

#: Seconds to wait for one completion. Generous on purpose: reasoning models
#: on a shared hosted endpoint have been measured taking several minutes to
#: answer a trivial prompt.
DEFAULT_TIMEOUT_S = 600.0


class OpenAICompatibleProvider(LLMProvider):
    """
    A real provider for an OpenAI-compatible ``/chat/completions`` endpoint.

    Args:
        model: Default model ID, used when a request does not name one.
        api_key: Bearer token for the service.
        base_url: Service base URL *including* the version path, e.g.
            ``https://integrate.api.nvidia.com/v1``.
        timeout_s: Seconds to wait for one completion.
        transport: Optional ``httpx`` transport, for tests.
        default_temperature: Temperature sent when a request does not set one
            (``None`` leaves the service's own default).

    Raises:
        LLMConfigurationError: *api_key* or *base_url* is empty.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
        default_temperature: float | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("An API key is required.")
        if not base_url:
            raise LLMConfigurationError("A base URL is required.")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._default_temperature = default_temperature
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_s, connect=15.0),
            transport=transport,
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate text via a real hosted model.

        Args:
            request: The provider-agnostic request. ``max_tokens`` and
                ``temperature`` are sent only when set. Note that for a
                reasoning model ``max_tokens`` also bounds the hidden
                reasoning, so a small value can leave no room for an answer.

        Returns:
            The generated :class:`~app.ai.providers.models.LLMResponse`.

        Raises:
            LLMConfigurationError: Key, model, or request rejected (4xx other
                than 429), or the reply was cut off before any answer.
            LLMProviderUnavailableError: Timeout, network failure, rate
                limit, server error, or an empty/malformed reply.
        """
        body: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "stream": False,
        }
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        temperature = (
            request.temperature
            if request.temperature is not None
            else self._default_temperature
        )
        if temperature is not None:
            body["temperature"] = temperature

        try:
            response = self._client.post(f"{self.base_url}/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LLMProviderUnavailableError(
                f"Timed out waiting for {self.base_url}: {type(exc).__name__}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderUnavailableError(
                f"Could not reach {self.base_url}: {type(exc).__name__}"
            ) from exc

        status = response.status_code
        if status >= 400:
            detail = _error_detail(response) or response.reason_phrase or "no detail"
            if status == 429 or status >= 500:
                raise LLMProviderUnavailableError(f"LLM API error ({status}): {detail}")
            raise LLMConfigurationError(
                f"LLM API rejected the request ({status}): {detail}"
            )

        try:
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMProviderUnavailableError(
                "LLM API returned a reply that could not be parsed."
            ) from exc

        if not content.strip():
            if choice.get("finish_reason") == "length":
                raise LLMConfigurationError(
                    "The model hit the token limit before producing an answer "
                    "(reasoning models spend max_tokens on reasoning too); "
                    "raise max_tokens."
                )
            raise LLMProviderUnavailableError("LLM API returned an empty answer.")

        usage = payload.get("usage") or {}
        counts = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
        return LLMResponse(
            text=content,
            model=payload.get("model") or request.model or self.model,
            usage={k: v for k, v in counts.items() if v is not None} or None,
        )


def _error_detail(response: httpx.Response) -> str:
    """A short, safe description of an error reply (never the request)."""
    try:
        data = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:200]
        for key in ("detail", "title", "message"):
            if data.get(key):
                return str(data[key])[:200]
    return response.text[:200]
