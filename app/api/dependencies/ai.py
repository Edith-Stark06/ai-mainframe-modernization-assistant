"""
AI API Dependencies.

Provides dependencies for injecting configured AI orchestrators and providers.
"""

from fastapi import Depends

from app.ai.documentation.service import DocumentationGenerationService
from app.ai.explanation.service import CodeExplanationService
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.ai.providers.base import LLMProvider
from app.ai.providers.ollama import OllamaProvider
from app.core.config import get_settings


def get_llm_provider() -> LLMProvider | None:
    """
    Returns the configured production LLM provider.

    Returns ``None`` (no provider configured) unless
    ``settings.llm_provider`` is explicitly set to ``"ollama"`` -- an
    operator must opt in, since Ollama may not be installed or running
    in every deployment; this endpoint must never silently assume a
    local model is available. When enabled, returns a real
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
    if settings.llm_provider != "ollama":
        return None
    return OllamaProvider(model=settings.ollama_model, host=settings.ollama_host)


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
