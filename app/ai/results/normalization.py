"""
AI Result Normalization.

Purpose:
    Normalizes a mutable/unstable `AIAnalysisResult` into an immutable,
    deterministic, and serialization-safe `NormalizedAIResult`.
"""

from typing import Any, Mapping

from app.ai.documentation.models import Documentation
from app.ai.explanation.models import CodeExplanation
from app.ai.orchestration.models import AIAnalysisResult
from app.ai.results.models import (
    AIArtifact,
    ArtifactType,
    ImmutableDict,
    NormalizedAIResult,
    NormalizedDocumentationPayload,
    NormalizedDocumentationSection,
    NormalizedExplanationPayload,
)


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
        explanation_payload = NormalizedExplanationPayload(
            summary=result.explanation.summary,
            explanation=result.explanation.explanation,
        )
        artifacts.append(
            AIArtifact(
                artifact_type=ArtifactType.EXPLANATION, payload=explanation_payload
            )
        )

    if result.documentation is not None:
        if not isinstance(result.documentation, Documentation):
            raise TypeError(
                f"Invalid payload for DOCUMENTATION: {type(result.documentation)}"
            )
        doc_payload = NormalizedDocumentationPayload(
            title=result.documentation.title,
            overview=result.documentation.overview,
            sections=tuple(
                NormalizedDocumentationSection(heading=s.heading, content=s.content)
                for s in result.documentation.sections
            ),
        )
        artifacts.append(
            AIArtifact(artifact_type=ArtifactType.DOCUMENTATION, payload=doc_payload)
        )

    if not artifacts:
        raise ValueError("Normalized result must contain at least one valid artifact.")

    # Deeply isolate the context
    isolated_context = _deep_isolate_context(result.context)

    return NormalizedAIResult(
        artifacts=tuple(artifacts),
        context=isolated_context,
    )


def _deep_isolate_context(context: Mapping[str, Any]) -> ImmutableDict:
    """
    Recursively isolates and normalizes the Phase-1 analysis context.
    - Dicts are deep copied and converted to ImmutableDict.
    - Sets are converted to sorted tuples.
    - Lists/Tuples are deep copied.
    - Domain Dataclasses are converted to dicts to prevent memory address leaks.
    """
    raw_dict = {k: _deep_serialize_value(v) for k, v in sorted(context.items())}
    # Initialize the ImmutableDict with the items. Once created, it cannot be modified.
    return ImmutableDict(raw_dict)


def _deep_serialize_value(value: Any) -> Any:
    """
    Recursively deep copies and normalizes values to ensure immutability,
    determinism, and JSON serialization safety.
    """
    if isinstance(value, dict) or type(value).__name__ == "MappingProxyType":
        return ImmutableDict(
            {k: _deep_serialize_value(v) for k, v in sorted(value.items())}
        )
    elif isinstance(value, (list, tuple)):
        return tuple(_deep_serialize_value(v) for v in value)
    elif isinstance(value, (set, frozenset)):
        serialized_items = [_deep_serialize_value(v) for v in value]

        # Sort serialized items deterministically using a structural string
        def sort_key(item: Any) -> str:
            import json

            # Convert to standard dict/list for json.dumps just in case
            def _to_std(val: Any) -> Any:
                if isinstance(val, Mapping):
                    return {k: _to_std(v) for k, v in val.items()}
                elif isinstance(val, tuple):
                    return [_to_std(v) for v in val]
                return val

            return json.dumps(_to_std(item), sort_keys=True)

        return tuple(sorted(serialized_items, key=sort_key))
    elif hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return ImmutableDict(
            {k: _deep_serialize_value(v) for k, v in sorted(asdict(value).items())}
        )
    elif (
        hasattr(value, "name")
        and hasattr(value, "value")
        and type(value).__name__ != "type"
    ):
        return value.name
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        return ImmutableDict(
            {k: _deep_serialize_value(v) for k, v in sorted(vars(value).items())}
        )
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value
    else:
        # Fallback for unrecognizable un-serializable objects (e.g. __slots__ only)
        qual_name = f"{value.__class__.__module__}.{value.__class__.__qualname__}"
        if hasattr(value, "__slots__"):
            state = {}
            for attr in value.__slots__:
                if hasattr(value, attr):
                    state[attr] = getattr(value, attr)
            return ImmutableDict(
                {
                    "__class__": qual_name,
                    **{k: _deep_serialize_value(v) for k, v in sorted(state.items())},
                }
            )
        return ImmutableDict({"__class__": qual_name})
