"""
AI Provider Errors

Provider-neutral exceptions for the LLM abstraction layer.
"""


class LLMProviderError(Exception):
    """Base exception for all AI provider errors."""

    pass


class LLMProviderUnavailableError(LLMProviderError):
    """Raised when the LLM provider is unavailable, times out, or fails internally."""

    pass


class LLMConfigurationError(LLMProviderError):
    """Raised when the LLM provider receives an invalid request or has invalid configuration."""

    pass
