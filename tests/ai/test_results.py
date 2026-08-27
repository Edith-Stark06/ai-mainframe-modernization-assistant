"""
Tests for Normalized AI Results.
"""

import json
from typing import Any

import pytest

from app.ai.documentation.models import Documentation, DocumentationSection
from app.ai.explanation.models import CodeExplanation
from app.ai.orchestration.models import AIAnalysisResult
from app.ai.results.models import (
    ArtifactType,
    ImmutableDict,
    NormalizedDocumentationPayload,
    NormalizedExplanationPayload,
)
from app.ai.results.normalization import normalize_result


def test_explanation_artifact() -> None:
    """It successfully normalizes a pure explanation result."""
    explanation = CodeExplanation(summary="Sum", explanation="Exp")
    raw_result = AIAnalysisResult(explanation=explanation, context={"a": 1})

    normalized = normalize_result(raw_result)
    assert len(normalized.artifacts) == 1
    assert normalized.artifacts[0].artifact_type == ArtifactType.EXPLANATION
    payload = normalized.get_explanation()
    assert isinstance(payload, NormalizedExplanationPayload)
    assert payload.summary == "Sum"
    assert payload.explanation == "Exp"
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
    payload = normalized.get_documentation()
    assert isinstance(payload, NormalizedDocumentationPayload)
    assert payload.title == "Title"
    assert payload.overview == "Over"
    assert len(payload.sections) == 1
    assert payload.sections[0].heading == "H"
    assert payload.sections[0].content == "C"
    assert normalized.get_explanation() is None
    assert normalized.context["b"] == 2


def test_combined_result_and_deterministic_ordering() -> None:
    """It deterministically orders artifacts: EXPLANATION then DOCUMENTATION."""
    exp = CodeExplanation(summary="Sum", explanation="Exp")
    doc = Documentation(title="T", overview="O", sections=())

    raw_result = AIAnalysisResult(documentation=doc, explanation=exp)
    normalized = normalize_result(raw_result)

    assert len(normalized.artifacts) == 2
    assert normalized.artifacts[0].artifact_type == ArtifactType.EXPLANATION
    assert normalized.artifacts[1].artifact_type == ArtifactType.DOCUMENTATION


def test_empty_result_validation() -> None:
    """It rejects results with no artifacts."""
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

    s1 = {"zebra", "apple", "mango"}
    s2 = {"apple", "mango", "zebra"}

    raw1 = AIAnalysisResult(explanation=exp, context={"items": s1})
    raw2 = AIAnalysisResult(explanation=exp, context={"items": s2})

    norm1 = normalize_result(raw1)
    norm2 = normalize_result(raw2)

    assert norm1.context["items"] == ("apple", "mango", "zebra")
    assert norm1.context == norm2.context

    # Test with unorderable objects without relying on memory addresses in their representations
    class Unorderable:
        def __init__(self, val: int):
            self.val = val

        def __eq__(self, other: Any) -> bool:
            return isinstance(other, Unorderable) and self.val == other.val

        def __hash__(self) -> int:
            return hash(self.val)

        # We explicitly omit __lt__ so it is unorderable
        def __str__(self) -> str:
            # Fake memory address using real id() to ensure different objects have different __str__
            return f"<Unorderable at 0x{id(self):016X}>"

        def __repr__(self) -> str:
            # Fake memory address using real id() to ensure different objects have different __repr__
            return f"<Unorderable object at 0x{id(self):016X}>"

    u1_a = Unorderable(1)
    u2_a = Unorderable(2)

    s3 = {u2_a, u1_a}
    raw3 = AIAnalysisResult(explanation=exp, context={"items": s3})
    norm3 = normalize_result(raw3)

    # 1. Normalization succeeds
    # 2. No fake address appears anywhere
    import json
    import re

    serialized_norm3 = json.dumps(norm3.to_dict())
    assert not re.search(r"0x[0-9A-F]{16}", serialized_norm3)

    # 3. Repeated normalization gives identical results
    norm3_repeated = normalize_result(raw3)
    assert norm3.context == norm3_repeated.context

    # 4. changing only __str__/__repr__ does not change normalized output
    # 5. ordering depends on stable attributes only
    u1_b = Unorderable(1)
    u2_b = Unorderable(2)
    # u1_b and u2_b have identical stable attributes, but different id() so different __str__/__repr__

    s4 = {u1_b, u2_b}
    raw4 = AIAnalysisResult(explanation=exp, context={"items": s4})
    norm4 = normalize_result(raw4)

    assert norm4.context == norm3.context


def test_input_immutability_and_deep_context_isolation() -> None:
    """It isolates nested mutable structures in the context, using ImmutableDict."""
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

    # Prove that the normalized dictionary itself is immutable
    with pytest.raises(TypeError):
        normalized.context["new"] = 1  # type: ignore

    with pytest.raises(TypeError):
        normalized.context["d"]["nested"] = 2  # type: ignore


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
    from enum import Enum

    class Color(Enum):
        RED = 1

    @dataclass
    class DomainModel:
        name: str
        value: int

    class CustomObj:
        def __init__(self):
            self.foo = "bar"

    domain_obj = DomainModel("test", 42)
    custom_obj = CustomObj()
    context: dict[str, Any] = {
        "domain": domain_obj,
        "color": Color.RED,
        "custom": custom_obj,
    }

    raw = AIAnalysisResult(explanation=exp, context=context)
    normalized = normalize_result(raw)

    # Verify everything converted to dicts/primitives correctly
    assert isinstance(normalized.context["domain"], ImmutableDict)
    assert normalized.context["domain"]["name"] == "test"
    assert normalized.context["domain"]["value"] == 42

    assert normalized.context["color"] == "RED"

    assert isinstance(normalized.context["custom"], ImmutableDict)
    assert normalized.context["custom"]["foo"] == "bar"

    # Verify it can be dumped to JSON without custom handlers
    json_str = json.dumps(normalized.context)
    assert "test" in json_str
    assert "RED" in json_str
    assert "bar" in json_str

    # Modify original domain obj
    domain_obj.name = "mutated"
    assert normalized.context["domain"]["name"] == "test"

    # Test complete result serialization via to_dict
    serialized_result = normalized.to_dict()
    assert "artifacts" in serialized_result
    assert len(serialized_result["artifacts"]) == 1
    assert serialized_result["artifacts"][0]["artifact_type"] == "EXPLANATION"
    assert serialized_result["artifacts"][0]["payload"]["summary"] == "Sum"

    # Prove that the entire output of to_dict is standard JSON serializable
    json.dumps(serialized_result)

    # Mixed Nesting Test
    nested_context = {"outer": {"items": ({"name": "A", "values": ("x", "y")},)}}
    raw_nested = AIAnalysisResult(explanation=exp, context=nested_context)
    normalized_nested = normalize_result(raw_nested)

    # Verify no mutable lists/dicts remain in context
    assert isinstance(normalized_nested.context, ImmutableDict)
    assert isinstance(normalized_nested.context["outer"], ImmutableDict)
    assert isinstance(normalized_nested.context["outer"]["items"], tuple)
    assert isinstance(normalized_nested.context["outer"]["items"][0], ImmutableDict)
    assert isinstance(normalized_nested.context["outer"]["items"][0]["values"], tuple)

    # original context can be mutated independently
    nested_context["outer"]["items"][0]["name"] = "mutated"  # type: ignore
    assert normalized_nested.context["outer"]["items"][0]["name"] == "A"

    # normalized.to_dict() produces ordinary dict/list primitives
    serialized_nested = normalized_nested.to_dict()
    assert isinstance(serialized_nested["context"], dict)
    assert isinstance(serialized_nested["context"]["outer"], dict)
    assert isinstance(serialized_nested["context"]["outer"]["items"], list)
    assert isinstance(serialized_nested["context"]["outer"]["items"][0], dict)
    assert isinstance(serialized_nested["context"]["outer"]["items"][0]["values"], list)
    assert serialized_nested["context"]["outer"]["items"][0]["name"] == "A"

    # json.dumps(...) succeeds
    json.dumps(serialized_nested)
