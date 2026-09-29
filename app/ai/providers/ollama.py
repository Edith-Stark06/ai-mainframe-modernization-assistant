"""
Ollama LLM Provider.

Purpose:
    A real, locally-hosted :class:`~app.ai.providers.base.LLMProvider`
    backed by `Ollama <https://ollama.com>`_, via the official
    ``ollama`` PyPI client (already a pinned project dependency).
    Before this module, ``LLMProvider`` had exactly one concrete
    implementation, :class:`~app.ai.providers.fake.FakeLLMProvider`
    -- ``get_llm_provider()`` (``app/api/dependencies/ai.py``) always
    returned ``None``, so no request in this codebase had ever
    actually reached a real model.

Responsibilities:
    - :class:`OllamaProvider` -- translates a provider-agnostic
      :class:`~app.ai.providers.models.LLMRequest` into an Ollama
      ``generate`` call and back into an
      :class:`~app.ai.providers.models.LLMResponse`, raising the
      correct provider-neutral error for a connection failure vs. a
      malformed request, per :class:`~app.ai.providers.base.LLMProvider`'s
      own documented contract.

Non-responsibilities:
    - Running or installing the Ollama server itself, or pulling
      models -- this class only talks to an already-running server at
      *host* over HTTP; if none is reachable, ``generate`` raises
      :class:`~app.ai.providers.errors.LLMProviderUnavailableError`,
      matching every other provider's contract, never a fabricated
      response.
    - Streaming responses -- ``stream=False`` always; a streaming
      variant is a separate, larger change to ``LLMResponse`` itself.

Dependencies:
    - ollama -- Client, RequestError, ResponseError

Examples:
    ::

        from app.ai.providers.ollama import OllamaProvider
        from app.ai.providers.models import LLMRequest

        provider = OllamaProvider(model="llama3.2:1b")
        response = provider.generate(LLMRequest(prompt="Say hello."))

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import ollama

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest, LLMResponse

__all__ = ["OllamaProvider"]


class OllamaProvider(LLMProvider):
    """
    A real Ollama-backed :class:`LLMProvider`.

    Args:
        model: The default Ollama model tag (e.g. ``"llama3.2:1b"``),
            used when a request does not specify its own ``model``.
        host: The Ollama server's base URL.
    """

    def __init__(
        self, model: str = "llama3", host: str = "http://localhost:11434"
    ) -> None:
        self.model = model
        self.host = host
        self._client = ollama.Client(host=host)

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate text via a real Ollama model.

        Args:
            request: The provider-agnostic request.

        Returns:
            The generated :class:`~app.ai.providers.models.LLMResponse`.

        Raises:
            LLMProviderUnavailableError: The Ollama server is
                unreachable, or itself reports a server-side failure.
            LLMConfigurationError: The request names a model or option
                Ollama rejects as invalid.
        """
        options: dict[str, float | int] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens

        try:
            result = self._client.generate(
                model=request.model or self.model,
                prompt=request.prompt,
                options=options or None,
                stream=False,
            )
        except ollama.RequestError as exc:
            raise LLMConfigurationError(str(exc)) from exc
        except ollama.ResponseError as exc:
            # A 4xx (e.g. 404 "model not found") is a client-side
            # mistake -- the configured model name is wrong, not the
            # server being down -- so it is a configuration error, not
            # an availability one. Anything else (5xx, or no status
            # code at all) is a genuine server-side failure.
            status = getattr(exc, "status_code", None)
            if status is not None and 400 <= status < 500:
                raise LLMConfigurationError(str(exc)) from exc
            raise LLMProviderUnavailableError(str(exc)) from exc
        except ConnectionError as exc:
            raise LLMProviderUnavailableError(
                f"Could not reach Ollama server at {self.host}: {exc}"
            ) from exc

        usage = {
            "prompt_tokens": result.prompt_eval_count,
            "completion_tokens": result.eval_count,
        }
        return LLMResponse(
            text=result.response or "",
            model=result.model or request.model or self.model,
            usage={k: v for k, v in usage.items() if v is not None} or None,
        )
