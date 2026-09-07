"""#118 — dataset example schema tests."""

from __future__ import annotations


import pytest
from pydantic import ValidationError

from app.dataset.schema import (
    DatasetExample,
    ExampleAnalysis,
    ExampleMetadata,
    GroundTruthStatus,
    Provenance,
    SourceLocation,
    TaskType,
    derive_example_id,
)
from tests.dataset.conftest import make_example


def test_derive_example_id_is_deterministic_and_stable() -> None:
    a = derive_example_id(TaskType.COBOL_EXPLANATION, "src", "v")
    b = derive_example_id(TaskType.COBOL_EXPLANATION, "src", "v")
    assert a == b
    assert a.startswith("cobol_explanation-")
    assert derive_example_id(TaskType.COBOL_EXPLANATION, "src", "w") != a
    assert derive_example_id(TaskType.RISK_IDENTIFICATION, "src", "v") != a


def test_valid_example_roundtrips() -> None:
    ex = make_example()
    data = ex.model_dump(mode="json")
    again = DatasetExample.model_validate(data)
    assert again == ex


def test_blank_source_rejected() -> None:
    with pytest.raises(ValidationError):
        make_example(source="   \n  ")


def test_empty_expected_output_rejected_for_required_task() -> None:
    with pytest.raises(ValidationError, match="expected_output is required"):
        make_example(expected={})


def test_invalid_task_type_rejected() -> None:
    with pytest.raises(ValidationError):
        DatasetExample.model_validate(
            {**make_example().model_dump(mode="json"), "task_type": "not_a_task"}
        )


def test_invalid_difficulty_rejected() -> None:
    with pytest.raises(ValidationError):
        DatasetExample.model_validate(
            {**make_example().model_dump(mode="json"), "difficulty": "trivial"}
        )


def test_source_sha_must_match() -> None:
    d = make_example().model_dump(mode="json")
    d["metadata"]["source_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="source_sha256"):
        DatasetExample.model_validate(d)


def test_metadata_source_id_must_match_input() -> None:
    d = make_example().model_dump(mode="json")
    d["metadata"]["source_id"] = "other"
    with pytest.raises(ValidationError, match="source_id"):
        DatasetExample.model_validate(d)


def test_source_location_past_end_rejected() -> None:
    with pytest.raises(ValidationError, match="past end of source"):
        make_example(source_locations=[SourceLocation(line=9999)])


def test_source_location_snippet_must_appear_verbatim() -> None:
    with pytest.raises(ValidationError, match="snippet not found"):
        make_example(
            source_locations=[SourceLocation(line=1, snippet="NOT IN THE SOURCE")]
        )


def test_analysis_fields_explicitly_optional_not_empty_dict() -> None:
    a = ExampleAnalysis()
    assert a.ast is None and a.dependencies is None and a.risks is None
    # None is not {} — a consumer can tell "not analysed" from "analysed, empty"
    d = a.model_dump()
    assert d["ast"] is None
    assert d["dependencies"] is None


def test_deterministic_ground_truth_requires_generated_or_fixture_provenance() -> None:
    with pytest.raises(ValidationError, match="ground_truth_status=deterministic"):
        ExampleMetadata(
            source_id="s",
            source_provenance=Provenance.SYNTHETIC,
            provenance=Provenance.MANUALLY_CURATED,
            license="MIT",
            generator_version="g",
            analysis_version="a",
            ground_truth_status=GroundTruthStatus.DETERMINISTIC,
            source_sha256="a" * 64,
        )


def test_two_provenance_axes_are_independent() -> None:
    ex = make_example(
        source_provenance=Provenance.SYNTHETIC,
        provenance=Provenance.DETERMINISTIC_GENERATED,
    )
    assert ex.metadata.source_provenance is Provenance.SYNTHETIC
    assert ex.metadata.provenance is Provenance.DETERMINISTIC_GENERATED


def test_dedup_key_ignores_id_and_metadata() -> None:
    a = make_example(variant="x")
    b = make_example(variant="y")  # different example_id
    assert a.example_id != b.example_id
    assert a.dedup_key() == b.dedup_key()
    c = make_example(expected={"answer": {"paragraph_count": 99}})
    assert c.dedup_key() != a.dedup_key()


def test_qa_question_survives_context() -> None:
    ex = make_example(
        task=TaskType.MODERNIZATION_QA, context={"question": "  What  strategy? "}
    )
    assert "strategy" in ex.input.context["question"].lower()
