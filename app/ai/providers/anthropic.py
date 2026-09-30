"""
Anthropic (Claude) LLM Provider.

Purpose:
    A real, hosted :class:`~app.ai.providers.base.LLMProvider` backed by the
    Anthropic Messages API, via the official ``anthropic`` PyPI client. It is
    the online counterpart of :class:`~app.ai.providers.ollama.OllamaProvider`:
    same provider-neutral request/response types, same error contract, chosen
    at runtime with ``LLM_PROVIDER=anthropic``.

Responsibilities:
    - :class:`AnthropicProvider` -- translates a provider-agnostic
      :class:`~app.ai.providers.models.LLMRequest` into a Messages API call and
      back into an :class:`~app.ai.providers.models.LLMResponse`, raising the
      provider-neutral error for a bad key/model/request
      (:class:`~app.ai.providers.errors.LLMConfigurationError`) versus a
      network, rate-limit, or server-side failure
      (:class:`~app.ai.providers.errors.LLMProviderUnavailableError`).

Non-responsibilities:
    - Storing credentials. The API key / auth token are passed in by the
      caller (from environment settings) and are never logged or put in an
      error message.
    - Streaming responses -- ``stream`` is never used.

Dependencies:
    - anthropic -- Anthropic client and its exception hierarchy

Examples:
    ::

        from app.ai.providers.anthropic import AnthropicProvider
        from app.ai.providers.models import LLMRequest

        provider = AnthropicProvider(model="claude-sonnet-5-5", api_key="...")
        response = provider.generate(LLMRequest(prompt="Say hello."))

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import anthropic

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest, LLMResponse

__all__ = ["AnthropicProvider"]

#: The Messages API requires ``max_tokens``; used when a request has none.
_DEFAULT_MAX_TOKENS = 2048

#: Seconds before a single API call is abandoned (the SDK default is ten
#: minutes, far longer than the UI's own request timeout).
_REQUEST_TIMEOUT_S = 120.0


class AnthropicProvider(LLMProvider):
    """
    A real Anthropic-backed :class:`LLMProvider`.

    Args:
        model: The default model ID (e.g. ``"claude-sonnet-5-5"``), used when
            a request does not specify its own ``model``.
        api_key: An Anthropic API key (sent as ``x-api-key``).
        auth_token: A bearer token, for gateways that authenticate that way.
            At least one of *api_key* / *auth_token* is required.
        base_url: Optional API base URL, for a proxy or gateway. ``None`` uses
            Anthropic's own endpoint.

    Raises:
        LLMConfigurationError: Neither *api_key* nor *auth_token* is given.
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        auth_token: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if not api_key and not auth_token:
            raise LLMConfigurationError(
                "Anthropic provider needs ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN."
            )
        self.model = model
        self._client = anthropic.Anthropic(
            api_key=api_key or None,
            auth_token=auth_token or None,
            base_url=base_url or None,
            timeout=_REQUEST_TIMEOUT_S,
            max_retries=2,
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate text via a real Claude model.

        Args:
            request: The provider-agnostic request.

        Returns:
            The generated :class:`~app.ai.providers.models.LLMResponse`.

        Raises:
            LLMConfigurationError: The key/token is rejected, or the model or
                request is invalid (a 4xx other than rate limiting).
            LLMProviderUnavailableError: The API is unreachable, rate
                limited, or reports a server-side failure.
        """
        params: dict[str, object] = {
            "model": request.model or self.model,
            "max_tokens": request.max_tokens or _DEFAULT_MAX_TOKENS,
            "messages": [{"role": "user", "content": request.prompt}],
        }

        try:
            message = self._client.messages.create(**params)  # type: ignore[call-overload]
        except anthropic.APIConnectionError as exc:
            # Includes timeouts (APITimeoutError is a subclass).
            raise LLMProviderUnavailableError(
                f"Could not reach the Anthropic API: {exc}"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise LLMProviderUnavailableError(
                f"Anthropic API rate limit reached: {exc}"
            ) from exc
        except anthropic.APIStatusError as exc:
            status = exc.status_code
            if status == 429 or status >= 500:  # 529 = overloaded
                raise LLMProviderUnavailableError(
                    f"Anthropic API error ({status}): {exc.message}"
                ) from exc
            raise LLMConfigurationError(
                f"Anthropic API rejected the request ({status}): {exc.message}"
            ) from exc

        text = "".join(block.text for block in message.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=message.model or request.model or self.model,
            usage={
                "prompt_tokens": message.usage.input_tokens,
                "completion_tokens": message.usage.output_tokens,
            },
        )
