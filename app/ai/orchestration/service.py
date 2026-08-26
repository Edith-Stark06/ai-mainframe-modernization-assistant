"""
AI Orchestration Service.

Coordinates execution of AI capabilities like code explanation and documentation generation,
while preserving input context.
"""

import copy
from typing import Any

from app.ai.documentation.service import DocumentationGenerationService
from app.ai.explanation.service import CodeExplanationService
from app.ai.orchestration.models import AIAnalysisResult, AICapability


class AIAnalysisOrchestrator:
    """
    Orchestrator for AI analysis capabilities.

    Coordinates the execution of specific AI services while preserving
    context. Failures in any requested service will fail the entire orchestration.
    """

    def __init__(
        self,
        explanation_service: CodeExplanationService,
        documentation_service: DocumentationGenerationService,
    ):
        self._explanation_service = explanation_service
        self._documentation_service = documentation_service

    def analyze(
        self,
        source: str,
        capabilities: set[AICapability],
        context: dict[str, Any] | None = None,
    ) -> AIAnalysisResult:
        """
        Run the requested AI capabilities for the provided source and context.

        Args:
            source: The COBOL source code.
            capabilities: A set of AICapability to execute.
            context: The Phase-1 analysis context (e.g. dependencies, business rules).

        Returns:
            AIAnalysisResult: The combined results of the executed capabilities.

        Raises:
            ValueError: If source is empty/whitespace, or if capabilities is empty.
            Exception: Any exception raised by the underlying AI services.
        """
        if not source or not source.strip():
            raise ValueError("COBOL source cannot be empty or whitespace-only.")

        if not capabilities:
            raise ValueError("At least one capability must be requested.")

        # Preserve the caller's context by creating a deepcopy
        preserved_context = copy.deepcopy(context) if context else {}

        explanation = None
        if AICapability.EXPLANATION in capabilities:
            explanation = self._explanation_service.explain_code(
                source, context=preserved_context
            )

        documentation = None
        if AICapability.DOCUMENTATION in capabilities:
            documentation = self._documentation_service.generate_documentation(
                source, context=preserved_context
            )

        return AIAnalysisResult(
            explanation=explanation,
            documentation=documentation,
            context=preserved_context,
        )
