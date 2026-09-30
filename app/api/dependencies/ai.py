"""
AI API Dependencies.

Provides dependencies for injecting configured AI orchestrators and providers.
"""

from fastapi import Depends
from loguru import logger

from app.ai.documentation.service import DocumentationGenerationService
from app.ai.explanation.service import CodeExplanationService
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import LLMProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.providers.ollama import OllamaProvider
from app.core.config import get_settings


def get_llm_provider() -> LLMProvider | None:
    """
    Returns the configured production LLM provider.

    Returns ``None`` (no provider configured) unless
    ``settings.llm_provider`` is explicitly set to ``"ollama"``,
    ``"nvidia"`` or ``"anthropic"`` -- an operator must opt in; this endpoint must never
    silently assume a model is available. ``"anthropic"`` without any
    credential is also "not configured" (``None``), never a provider that
    would fail on every call. When ``"ollama"`` is enabled, returns a real
    :class:`~app.ai.providers.ollama.OllamaProvider` (constructing it
    does not itself contact the server -- a genuine outage still
    surfaces as ``LLMProviderUnavailableError`` on the first real
    request, never a fabricated response). Not cached -- unlike
    :func:`app.api.dependencies.rag.get_embedding_provider`'s real
    model load, constructing an ``OllamaProvider`` is cheap (a lazy
    HTTP client wrapper), so this stays a plain per-request call and
    correctly reflects ``settings.llm_provider`` changing at runtime
    (e.g. across tests) rather than caching a stale answer forever.
    Tests override this dependency to inject fake providers.
    """
    settings = get_settings()
    if settings.llm_provider == "ollama":
        return OllamaProvider(model=settings.ollama_model, host=settings.ollama_host)
    if settings.llm_provider == "nvidia":
        nvidia_key = (
            settings.nvidia_api_key.get_secret_value().strip()
            if settings.nvidia_api_key
            else ""
        )
        if not nvidia_key:
            logger.warning(
                "LLM_PROVIDER=nvidia but NVIDIA_API_KEY is not set; treating "
                "the LLM as not configured."
            )
            return None
        return OpenAICompatibleProvider(
            model=settings.nvidia_model,
            api_key=nvidia_key,
            base_url=settings.nvidia_base_url.strip(),
            timeout_s=settings.nvidia_timeout_s,
        )
    if settings.llm_provider == "anthropic":
        api_key = (
            settings.anthropic_api_key.get_secret_value().strip()
            if settings.anthropic_api_key
            else ""
        )
        auth_token = (
            settings.anthropic_auth_token.get_secret_value().strip()
            if settings.anthropic_auth_token
            else ""
        )
        if not api_key and not auth_token:
            logger.warning(
                "LLM_PROVIDER=anthropic but neither ANTHROPIC_API_KEY nor "
                "ANTHROPIC_AUTH_TOKEN is set; treating the LLM as not configured."
            )
            return None
        return AnthropicProvider(
            model=settings.anthropic_model,
            api_key=api_key or None,
            auth_token=auth_token or None,
            base_url=settings.anthropic_base_url.strip() or None,
        )
    return None


def get_ai_orchestrator(
    provider: LLMProvider | None = Depends(get_llm_provider),
) -> AIAnalysisOrchestrator | None:
    """
    Provides the AI Analysis Orchestrator initialized with the active LLM provider.
    Returns None if no provider is configured.
    """
    if provider is None:
        return None

    return AIAnalysisOrchestrator(
        explanation_service=CodeExplanationService(provider),
        documentation_service=DocumentationGenerationService(provider),
    )
