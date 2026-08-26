"""
Normalized AI Result Models.

Purpose:
    Define a stable, provider-independent, and immutable representation
    of AI analysis results.
"""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from app.ai.documentation.models import Documentation
from app.ai.explanation.models import CodeExplanation


class ArtifactType(str, Enum):
    """
    Types of supported AI artifacts.
    """

    EXPLANATION = "EXPLANATION"
    DOCUMENTATION = "DOCUMENTATION"


@dataclass(frozen=True)
class AIArtifact:
    """
    An immutable wrapper for a specific AI artifact.
    """

    artifact_type: ArtifactType
    payload: CodeExplanation | Documentation


@dataclass(frozen=True)
class NormalizedAIResult:
    """
    A deterministic, immutable container for normalized AI results.
    """

    artifacts: tuple[AIArtifact, ...]
    context: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def get_explanation(self) -> CodeExplanation | None:
        """
        Extract the explanation artifact if present.
        """
        for artifact in self.artifacts:
            if artifact.artifact_type == ArtifactType.EXPLANATION:
                return artifact.payload  # type: ignore
        return None

    def get_documentation(self) -> Documentation | None:
        """
        Extract the documentation artifact if present.
        """
        for artifact in self.artifacts:
            if artifact.artifact_type == ArtifactType.DOCUMENTATION:
                return artifact.payload  # type: ignore
        return None
