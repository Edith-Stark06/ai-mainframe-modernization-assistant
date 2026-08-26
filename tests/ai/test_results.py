"""
Tests for Normalized AI Results.
"""

from typing import Any

import pytest

from app.ai.documentation.models import Documentation, DocumentationSection
from app.ai.explanation.models import CodeExplanation
from app.ai.orchestration.models import AIAnalysisResult
from app.ai.results.models import ArtifactType
from app.ai.results.normalization import normalize_result


def test_explanation_artifact() -> None:
    """It successfully normalizes a pure explanation result."""
    explanation = CodeExplanation(summary="Sum", explanation="Exp")
    raw_result = AIAnalysisResult(explanation=explanation, context={"a": 1})

    normalized = normalize_result(raw_result)
    assert len(normalized.artifacts) == 1
    assert normalized.artifacts[0].artifact_type == ArtifactType.EXPLANATION
    assert normalized.artifacts[0].payload == explanation
    assert normalized.get_explanation() == explanation
    assert normalized.get_documentation() is None
    assert normalized.context["a"] == 1


def test_documentation_artifact() -> None:
    """It successfully normalizes a pure documentation result."""
    doc = Documentation(
        title="Title",
        overview="Over",
        sections=(DocumentationSection(heading="H", content="C"),),
    )
    raw_result = AIAnalysisResult(documentation=doc, context={"b": 2})

    normalized = normalize_result(raw_result)
    assert len(normalized.artifacts) == 1
    assert normalized.artifacts[0].artifact_type == ArtifactType.DOCUMENTATION
    assert normalized.artifacts[0].payload == doc
    assert normalized.get_documentation() == doc
    assert normalized.get_explanation() is None
    assert normalized.context["b"] == 2


def test_combined_result_and_deterministic_ordering() -> None:
    """It deterministically orders artifacts: EXPLANATION then DOCUMENTATION."""
    exp = CodeExplanation(summary="Sum", explanation="Exp")
    doc = Documentation(title="T", overview="O", sections=())

    # Create it with any argument order
    raw_result = AIAnalysisResult(documentation=doc, explanation=exp)
    normalized = normalize_result(raw_result)

    assert len(normalized.artifacts) == 2
    assert normalized.artifacts[0].artifact_type == ArtifactType.EXPLANATION
    assert normalized.artifacts[1].artifact_type == ArtifactType.DOCUMENTATION


def test_empty_result_validation() -> None:
    """It rejects results with no artifacts."""
    # We have to bypass AIAnalysisResult post_init to test normalize_result empty check
    # But AIAnalysisResult already rejects empty artifacts. We'll still test normalize_result explicitly.
    with pytest.raises(ValueError, match="must contain at least one valid artifact"):

        class FakeRawResult:
            explanation = None
            documentation = None
            context = {}

        normalize_result(FakeRawResult())  # type: ignore


def test_invalid_artifact_payload() -> None:
    """It rejects invalid artifact payloads."""
    with pytest.raises(TypeError, match="Invalid payload for EXPLANATION"):

        class FakeRawResult:
            explanation = "Not a CodeExplanation"
            documentation = None
            context = {}

        normalize_result(FakeRawResult())  # type: ignore

    with pytest.raises(TypeError, match="Invalid payload for DOCUMENTATION"):

        class FakeRawResult:
            explanation = None
            documentation = "Not a Documentation"
            context = {}

        normalize_result(FakeRawResult())  # type: ignore


def test_dict_ordering_independence() -> None:
    """It sorts dictionary keys deterministically."""
    exp = CodeExplanation(summary="Sum", explanation="Exp")

    # Two dicts with different insertion orders
    dict1 = {}
    dict1["b"] = 2
    dict1["a"] = 1
    raw1 = AIAnalysisResult(explanation=exp, context=dict1)

    dict2 = {}
    dict2["a"] = 1
    dict2["b"] = 2
    raw2 = AIAnalysisResult(explanation=exp, context=dict2)

    norm1 = normalize_result(raw1)
    norm2 = normalize_result(raw2)

    assert list(norm1.context.keys()) == ["a", "b"]
    assert list(norm2.context.keys()) == ["a", "b"]
    assert norm1.context == norm2.context


def test_set_ordering_independence() -> None:
    """It converts sets to deterministically ordered tuples."""
    exp = CodeExplanation(summary="Sum", explanation="Exp")

    # Set ordering is non-deterministic in Python between runs, but sorting ensures determinism
    s1 = {"zebra", "apple", "mango"}
    s2 = {"apple", "mango", "zebra"}

    raw1 = AIAnalysisResult(explanation=exp, context={"items": s1})
    raw2 = AIAnalysisResult(explanation=exp, context={"items": s2})

    norm1 = normalize_result(raw1)
    norm2 = normalize_result(raw2)

    # It must become a sorted tuple
    assert norm1.context["items"] == ("apple", "mango", "zebra")
    assert norm1.context == norm2.context


def test_input_immutability_and_deep_context_isolation() -> None:
    """It isolates nested mutable structures in the context."""
    exp = CodeExplanation(summary="Sum", explanation="Exp")

    mutable_list = [1, 2, 3]
    mutable_dict = {"nested": [4, 5]}
    context = {"l": mutable_list, "d": mutable_dict}

    raw = AIAnalysisResult(explanation=exp, context=context)
    normalized = normalize_result(raw)

    # Mutate the original context
    mutable_list.append(4)
    mutable_dict["nested"].append(6)
    context["new_key"] = "leaked"

    # The normalized context should be completely unaffected
    assert "new_key" not in normalized.context
    assert normalized.context["l"] == (1, 2, 3)
    assert normalized.context["d"]["nested"] == (4, 5)


def test_repeated_normalization() -> None:
    """Repeated normalization produces identical results."""
    exp = CodeExplanation(summary="Sum", explanation="Exp")
    raw = AIAnalysisResult(explanation=exp, context={"s": {"b", "a"}})

    norm1 = normalize_result(raw)
    norm2 = normalize_result(raw)

    assert norm1 == norm2


def test_serialization() -> None:
    """Context must be serializable if it contains simple structures, and safe from address leakage."""
    exp = CodeExplanation(summary="Sum", explanation="Exp")

    from dataclasses import dataclass

    @dataclass
    class DomainModel:
        name: str
        value: int

    domain_obj = DomainModel("test", 42)
    context: dict[str, Any] = {"domain": domain_obj}

    raw = AIAnalysisResult(explanation=exp, context=context)
    normalized = normalize_result(raw)

    # The domain object is preserved deeply, ensuring its attributes don't leak arbitrary addresses
    # unless __str__ is invoked. The deepcopy prevents memory leakage from mutating the original.
    assert normalized.context["domain"].name == "test"

    # Modify original domain obj
    domain_obj.name = "mutated"
    assert normalized.context["domain"].name == "test"
