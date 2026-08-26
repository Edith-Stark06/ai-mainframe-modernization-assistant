"""
AI Result Normalization.

Purpose:
    Normalizes a mutable/unstable `AIAnalysisResult` into an immutable,
    deterministic, and serialization-safe `NormalizedAIResult`.
"""

import copy
from types import MappingProxyType
from typing import Any, Mapping

from app.ai.documentation.models import Documentation
from app.ai.explanation.models import CodeExplanation
from app.ai.orchestration.models import AIAnalysisResult
from app.ai.results.models import AIArtifact, ArtifactType, NormalizedAIResult


def normalize_result(result: AIAnalysisResult) -> NormalizedAIResult:
    """
    Normalizes an AI orchestration result into a deterministic representation.

    Args:
        result: The raw orchestration result.

    Returns:
        An immutable and deterministic NormalizedAIResult.

    Raises:
        ValueError: If no valid artifacts are present in the result.
        TypeError: If an artifact payload has an invalid type.
    """
    artifacts: list[AIArtifact] = []

    # Deterministic artifact ordering: EXPLANATION then DOCUMENTATION
    if result.explanation is not None:
        if not isinstance(result.explanation, CodeExplanation):
            raise TypeError(
                f"Invalid payload for EXPLANATION: {type(result.explanation)}"
            )
        artifacts.append(
            AIArtifact(
                artifact_type=ArtifactType.EXPLANATION, payload=result.explanation
            )
        )

    if result.documentation is not None:
        if not isinstance(result.documentation, Documentation):
            raise TypeError(
                f"Invalid payload for DOCUMENTATION: {type(result.documentation)}"
            )
        artifacts.append(
            AIArtifact(
                artifact_type=ArtifactType.DOCUMENTATION, payload=result.documentation
            )
        )

    if not artifacts:
        raise ValueError("Normalized result must contain at least one valid artifact.")

    # Deeply isolate the context
    isolated_context = _deep_isolate_context(result.context)

    return NormalizedAIResult(
        artifacts=tuple(artifacts),
        context=MappingProxyType(isolated_context),
    )


def _deep_isolate_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """
    Recursively isolates and normalizes the Phase-1 analysis context.
    - Dicts are deep copied and keys are sorted.
    - Sets are converted to sorted tuples.
    - Lists/Tuples are deep copied.
    - Domain Dataclasses are deeply copied.
    """
    return {k: _deep_serialize_value(v) for k, v in sorted(context.items())}


def _deep_serialize_value(value: Any) -> Any:
    """
    Recursively deep copies and normalizes values to ensure immutability
    and determinism.
    """
    if isinstance(value, (dict, MappingProxyType)):
        return {k: _deep_serialize_value(v) for k, v in sorted(value.items())}
    elif isinstance(value, (list, tuple)):
        return tuple(_deep_serialize_value(v) for v in value)
    elif isinstance(value, frozenset):
        return tuple(_deep_serialize_value(v) for v in _sort_set_or_frozenset(value))
    elif isinstance(value, set):
        return tuple(_deep_serialize_value(v) for v in _sort_set_or_frozenset(value))
    elif hasattr(value, "__dataclass_fields__"):
        # Explicit deep copy for domain dataclasses to avoid memory address leakage
        # while preserving domain structures required by downstream API/routers.
        return copy.deepcopy(value)
    else:
        # Primitives or base objects without state
        return value


def _sort_set_or_frozenset(s: set[Any] | frozenset[Any]) -> list[Any]:
    """
    Sorts a set/frozenset deterministically, falling back to string representation
    if elements are inherently unorderable.
    """
    try:
        return sorted(list(s))
    except TypeError:
        return sorted(list(s), key=str)
