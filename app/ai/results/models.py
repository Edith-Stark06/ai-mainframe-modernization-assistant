"""
Normalized AI Result Models.

Purpose:
    Define a stable, provider-independent, and immutable representation
    of AI analysis results.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ImmutableDict(dict):
    """
    An immutable dictionary that can be natively serialized by JSON.
    """

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("Immutable mapping")

    def __delitem__(self, key: Any) -> None:
        raise TypeError("Immutable mapping")

    def clear(self) -> None:
        raise TypeError("Immutable mapping")

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("Immutable mapping")

    def popitem(self) -> Any:
        raise TypeError("Immutable mapping")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("Immutable mapping")

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("Immutable mapping")

    def __deepcopy__(self, memo: dict[int, Any]) -> "ImmutableDict":
        # Contents are always fully, recursively frozen at construction time
        # (see _deep_isolate_context/_deep_serialize_value), so there is
        # nothing left to protect against mutation. Returning self avoids the
        # default deepcopy reconstruction path, which calls __setitem__ on a
        # fresh instance and would raise.
        return self


class ArtifactType(str, Enum):
    """
    Types of supported AI artifacts.
    """

    EXPLANATION = "EXPLANATION"
    DOCUMENTATION = "DOCUMENTATION"


@dataclass(frozen=True)
class NormalizedExplanationPayload:
    summary: str
    explanation: str


@dataclass(frozen=True)
class NormalizedDocumentationSection:
    heading: str
    content: str


@dataclass(frozen=True)
class NormalizedDocumentationPayload:
    title: str
    overview: str
    sections: tuple[NormalizedDocumentationSection, ...]


@dataclass(frozen=True)
class AIArtifact:
    """
    An immutable wrapper for a specific normalized AI artifact.
    """

    artifact_type: ArtifactType
    payload: NormalizedExplanationPayload | NormalizedDocumentationPayload


@dataclass(frozen=True)
class NormalizedAIResult:
    """
    A deterministic, immutable container for normalized AI results.
    """

    artifacts: tuple[AIArtifact, ...]
    context: Mapping[str, Any]

    def get_explanation(self) -> NormalizedExplanationPayload | None:
        """
        Extract the explanation payload if present.
        """
        for artifact in self.artifacts:
            if artifact.artifact_type == ArtifactType.EXPLANATION:
                return artifact.payload  # type: ignore
        return None

    def get_documentation(self) -> NormalizedDocumentationPayload | None:
        """
        Extract the documentation payload if present.
        """
        for artifact in self.artifacts:
            if artifact.artifact_type == ArtifactType.DOCUMENTATION:
                return artifact.payload  # type: ignore
        return None

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the normalized result to a standard JSON-compatible dictionary.
        """
        import dataclasses

        def _serialize_artifact(artifact: AIArtifact) -> dict[str, Any]:
            payload_dict = dataclasses.asdict(artifact.payload)
            return {
                "artifact_type": artifact.artifact_type.value,
                "payload": payload_dict,
            }

        def _to_json_compatible(val: Any) -> Any:
            """Recursively convert ImmutableDict/tuple back to normal dict/list for strict JSON serialization."""
            if isinstance(val, Mapping):
                return {k: _to_json_compatible(v) for k, v in val.items()}
            elif isinstance(val, (tuple, list)):
                return [_to_json_compatible(v) for v in val]
            return val

        return {
            "artifacts": [_serialize_artifact(a) for a in self.artifacts],
            "context": _to_json_compatible(self.context),
        }
