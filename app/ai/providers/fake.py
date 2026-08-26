"""
Deterministic Fake LLM Provider

A predictable, network-free implementation of LLMProvider for unit tests.
"""

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMConfigurationError, LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest, LLMResponse


class FakeLLMProvider(LLMProvider):
    """
    A deterministic fake provider for testing.

    Args:
        response_text: The static text to return for any prompt, unless simulate_failure or simulate_invalid_config are set.
        simulate_failure: If True, generate() raises LLMProviderUnavailableError.
        simulate_invalid_config: If True, generate() raises LLMConfigurationError.
    """

    def __init__(
        self,
        response_text: str = "Fake generated text",
        simulate_failure: bool = False,
        simulate_invalid_config: bool = False,
    ) -> None:
        self.response_text = response_text
        self.simulate_failure = simulate_failure
        self.simulate_invalid_config = simulate_invalid_config
        self.last_request: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request

        if self.simulate_invalid_config:
            raise LLMConfigurationError("Simulated invalid configuration or request.")

        if self.simulate_failure:
            raise LLMProviderUnavailableError("Simulated provider failure.")

        return LLMResponse(
            text=self.response_text,
            model=request.model or "fake-model",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
