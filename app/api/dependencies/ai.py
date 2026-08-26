"""
AI API Dependencies.

Provides dependencies for injecting configured AI orchestrators and providers.
"""

from fastapi import Depends

from app.ai.documentation.service import DocumentationGenerationService
from app.ai.explanation.service import CodeExplanationService
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.ai.providers.base import LLMProvider


def get_llm_provider() -> LLMProvider:
    """
    Returns the configured production LLM provider.

    Raises NotImplementedError as the production provider is not yet configured.
    Tests override this dependency to inject fake providers.
    """
    raise NotImplementedError("Production LLM provider is not yet configured.")


def get_ai_orchestrator(
    provider: LLMProvider = Depends(get_llm_provider),
) -> AIAnalysisOrchestrator:
    """
    Provides the AI Analysis Orchestrator initialized with the active LLM provider.
    """
    return AIAnalysisOrchestrator(
        explanation_service=CodeExplanationService(provider),
        documentation_service=DocumentationGenerationService(provider),
    )
