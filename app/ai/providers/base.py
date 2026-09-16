"""
AI Provider Base Protocol

Defines the contract for LLM providers.
"""

from typing import Protocol, runtime_checkable

from app.ai.providers.models import LLMRequest, LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    """
    Provider-agnostic interface for generating text from an LLM.
    Any concrete provider (OpenAI, Anthropic, Ollama, etc.) must implement this interface.
    """

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Generate text from the LLM based on the given request.

        Args:
            request: The provider-agnostic request containing the prompt and optional configuration.

        Returns:
            The generated response from the provider.

        Raises:
            LLMProviderUnavailableError: If the provider is unreachable or fails.
            LLMConfigurationError: If the request or provider configuration is invalid.
        """
        ...
