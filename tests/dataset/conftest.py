"""Shared helpers for Phase 6 dataset tests."""

from __future__ import annotations

import hashlib

import pytest

from app.dataset.builder import DatasetBuilder
from app.dataset.corpus import load_phase6_corpus
from app.dataset.schema import (
    DatasetExample,
    Difficulty,
    ExampleAnalysis,
    ExampleInput,
    ExampleMetadata,
    GroundTruthStatus,
    Provenance,
    TaskType,
    derive_example_id,
)
from app.dataset.version import ANALYSIS_VERSION, DATASET_VERSION, GENERATOR_VERSION

_TRIVIAL = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. T.\n"
    "       PROCEDURE DIVISION.\n"
    "       MAIN.\n"
    "           DISPLAY 'HI'.\n"
    "           STOP RUN.\n"
)


def make_example(
    *,
    source: str = _TRIVIAL,
    source_id: str = "s1",
    task: TaskType = TaskType.SOURCE_GROUNDED_QA,
    difficulty: Difficulty = Difficulty.EASY,
    expected: dict | None = None,
    context: dict | None = None,
    analysis: ExampleAnalysis | None = None,
    provenance: Provenance = Provenance.DETERMINISTIC_GENERATED,
    source_provenance: Provenance = Provenance.REPOSITORY_FIXTURE,
    gt: GroundTruthStatus = GroundTruthStatus.DETERMINISTIC,
    variant: str = "",
    source_locations=None,
) -> DatasetExample:
    ctx = context if context is not None else {"question": "how many paragraphs?"}
    return DatasetExample(
        example_id=derive_example_id(task, source_id, variant),
        dataset_version=DATASET_VERSION,
        task_type=task,
        difficulty=difficulty,
        input=ExampleInput(source=source, source_id=source_id, context=ctx),
        analysis=analysis or ExampleAnalysis(ast={"type": "ProgramNode"}),
        expected_output=(
            expected if expected is not None else {"answer": {"paragraph_count": 1}}
        ),
        source_locations=source_locations or [],
        metadata=ExampleMetadata(
            source_id=source_id,
            source_provenance=source_provenance,
            provenance=provenance,
            license="MIT",
            generator_version=GENERATOR_VERSION,
            analysis_version=ANALYSIS_VERSION,
            ground_truth_status=gt,
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        ),
    )


@pytest.fixture(scope="session")
def built_dataset(tmp_path_factory):
    """The full corpus built once (deterministic, fixed timestamp)."""
    work = tmp_path_factory.mktemp("phase6-build")
    builder = DatasetBuilder(work_dir=work, created_at="2026-01-01T00:00:00Z")
    return builder.build(load_phase6_corpus())
