"""
AI Orchestration Models.

Defines the capabilities and the structured orchestration result.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from app.ai.documentation.models import Documentation
from app.ai.explanation.models import CodeExplanation


class AICapability(Enum):
    """
    Capabilities available for AI orchestration.
    """

    EXPLANATION = auto()
    DOCUMENTATION = auto()


@dataclass(frozen=True)
class AIAnalysisResult:
    """
    Immutable representation of combined AI analysis artifacts.

    Attributes:
        explanation: The generated explanation, or None if not requested.
        documentation: The generated documentation, or None if not requested.
        context: Immutable snapshot of the Phase-1 analysis context provided to the orchestrator.
    """

    explanation: CodeExplanation | None = None
    documentation: Documentation | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.explanation is None and self.documentation is None:
            raise ValueError(
                "AIAnalysisResult must contain at least one successful artifact."
            )
