"""Tests for the MMIM-v1 dataset generation, schema, and quality gates.

Verifies:
- Task example generation across the MMIM taxonomy
- Schema conformance and provenance tracking
- Source hashing and location validity
- Deterministic regeneration
- Zero benchmark leakage (source ID, SHA, normalized SHA)
- Zero train/val/test split leakage
- Duplicate example ID detection
- Strict behavioral validation / ground-truth labeling
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.benchmark.suite import load_benchmark
from app.dataset.corpus import (
    SourceRecord,
    load_training_corpus,
)
from app.dataset.io import read_examples
from app.dataset.leakage import detect_leakage
from app.dataset.mmim_builder import MMIMDatasetBuilder, build_mmim_dataset
from app.dataset.schema import (
    DatasetExample,
    Difficulty,
    GroundTruthStatus,
    Provenance,
    TaskType,
)
from app.dataset.version import BENCHMARK_VERSION, MMIM_DATASET_VERSION

MMIM_DATASET_DIR = Path("data/dataset/mmim-v1")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


@pytest.fixture(scope="module")
def mmim_all_examples() -> list[DatasetExample]:
    path = MMIM_DATASET_DIR / "all.jsonl"
    if not path.exists():
        build_mmim_dataset(MMIM_DATASET_DIR, load_training_corpus(), seed=42)
    return read_examples(path)


@pytest.fixture(scope="module")
def mmim_splits() -> dict[str, list[DatasetExample]]:
    return {
        "train": read_examples(MMIM_DATASET_DIR / "train.jsonl"),
        "validation": read_examples(MMIM_DATASET_DIR / "validation.jsonl"),
        "test": read_examples(MMIM_DATASET_DIR / "test.jsonl"),
    }


@pytest.fixture(scope="module")
def benchmark():
    return load_benchmark(BENCHMARK_VERSION)


# --------------------------------------------------------------------------
# 1. MMIM Task Generation & Taxonomy
# --------------------------------------------------------------------------


def test_mmim_task_taxonomy_types():
    expected_tasks = {
        TaskType.PROGRAM_UNDERSTANDING,
        TaskType.BUSINESS_RULE_EXTRACTION,
        TaskType.DEPENDENCY_REASONING,
        TaskType.RISK_CLASSIFICATION,
        TaskType.MODERNIZATION_STRATEGY,
        TaskType.TRANSFORMATION_PLANNING,
        TaskType.COBOL_TO_JAVA,
        TaskType.VALIDATION_REASONING,
    }
    for task in expected_tasks:
        assert isinstance(task.value, str)
        assert len(task.value) > 0


def test_builder_generates_all_task_types_for_sample(tmp_path):
    builder = MMIMDatasetBuilder(work_dir=tmp_path)
    sample_source = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-COUNT PIC 9(2) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-COUNT > 0
               DISPLAY "POSITIVE"
           ELSE
               DISPLAY "ZERO"
           END-IF
           STOP RUN.
"""
    rec = SourceRecord(
        source_id="test_hello",
        source=sample_source,
        provenance=Provenance.SYNTHETIC,
        license="MIT",
        difficulty=Difficulty.EASY,
    )
    result = builder.build([rec])
    examples = result.examples
    task_types = {e.task_type for e in examples}

    assert TaskType.PROGRAM_UNDERSTANDING in task_types
    assert TaskType.BUSINESS_RULE_EXTRACTION in task_types
    assert TaskType.DEPENDENCY_REASONING in task_types
    assert TaskType.RISK_CLASSIFICATION in task_types
    assert TaskType.MODERNIZATION_STRATEGY in task_types
    assert TaskType.TRANSFORMATION_PLANNING in task_types
    assert TaskType.COBOL_TO_JAVA in task_types
    assert TaskType.VALIDATION_REASONING in task_types


# --------------------------------------------------------------------------
# 2. Schema Validation & Integrity
# --------------------------------------------------------------------------


def test_all_examples_conform_to_schema(mmim_all_examples):
    assert len(mmim_all_examples) > 0
    for ex in mmim_all_examples:
        assert ex.example_id.strip() != ""
        assert ex.dataset_version == MMIM_DATASET_VERSION
        assert ex.input.source_id.strip() != ""
        assert len(ex.input.source) > 0
        assert len(ex.metadata.source_sha256) == 64
        assert ex.expected_output is not None
        assert ex.metadata.provenance in Provenance
        assert ex.metadata.ground_truth_status in GroundTruthStatus


def test_all_source_hashes_match_content(mmim_all_examples):
    for ex in mmim_all_examples:
        actual_sha = _sha(ex.input.source)
        assert (
            ex.metadata.source_sha256 == actual_sha
        ), f"SHA mismatch for {ex.example_id}: {ex.metadata.source_sha256} != {actual_sha}"


def test_locations_are_valid_in_source(mmim_all_examples):
    for ex in mmim_all_examples:
        lines = ex.input.source.splitlines()
        for loc in ex.source_locations:
            assert loc.line >= 1
            assert (
                loc.line <= len(lines) + 1
            ), f"Location line {loc.line} exceeds total lines {len(lines)} in {ex.example_id}"


def test_no_duplicate_example_ids(mmim_all_examples):
    ids = [e.example_id for e in mmim_all_examples]
    assert len(ids) == len(set(ids)), f"Duplicate IDs found: {len(ids) - len(set(ids))}"


# --------------------------------------------------------------------------
# 3. Provenance and Ground-Truth Status
# --------------------------------------------------------------------------


def test_ground_truth_status_contract(mmim_all_examples):
    for ex in mmim_all_examples:
        gt = ex.metadata.ground_truth_status
        if ex.task_type == TaskType.COBOL_TO_JAVA:
            assert gt in {
                GroundTruthStatus.EXECUTABLE_VERIFIED,
                GroundTruthStatus.DETERMINISTIC,
                GroundTruthStatus.REVIEWED,
            }
            if gt == GroundTruthStatus.EXECUTABLE_VERIFIED:
                java_src = (
                    ex.expected_output.get("java")
                    or ex.expected_output.get("java_code")
                    or ""
                )
                assert "class " in java_src
        else:
            assert gt in {
                GroundTruthStatus.DETERMINISTIC,
                GroundTruthStatus.REVIEWED,
            }


# --------------------------------------------------------------------------
# 4. Deterministic Regeneration
# --------------------------------------------------------------------------


def test_deterministic_regeneration(tmp_path):
    corpus = load_training_corpus()[:2]
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    res1, _, _, _ = build_mmim_dataset(out1, corpus, seed=42)
    res2, _, _, _ = build_mmim_dataset(out2, corpus, seed=42)

    ids1 = [e.example_id for e in res1.examples]
    ids2 = [e.example_id for e in res2.examples]
    assert ids1 == ids2

    ex1_dumps = [e.model_dump_json() for e in res1.examples]
    ex2_dumps = [e.model_dump_json() for e in res2.examples]
    assert ex1_dumps == ex2_dumps


# --------------------------------------------------------------------------
# 5. Benchmark Leakage Isolation
# --------------------------------------------------------------------------


def test_zero_benchmark_source_overlap(benchmark, mmim_all_examples):
    bench_ids = {e.input.source_id for e in benchmark.examples}
    mmim_ids = {e.input.source_id for e in mmim_all_examples}
    overlap = bench_ids & mmim_ids
    assert overlap == set(), f"Benchmark source ID overlap: {overlap}"


def test_zero_benchmark_hash_overlap(benchmark, mmim_all_examples):
    bench_sha = {_sha(e.input.source) for e in benchmark.examples}
    mmim_sha = {_sha(e.input.source) for e in mmim_all_examples}
    overlap = bench_sha & mmim_sha
    assert overlap == set(), f"Benchmark source SHA overlap: {overlap}"


def test_zero_benchmark_normalized_overlap(benchmark, mmim_all_examples):
    bench_norm = {_sha(_norm(e.input.source)) for e in benchmark.examples}
    mmim_norm = {_sha(_norm(e.input.source)) for e in mmim_all_examples}
    overlap = bench_norm & mmim_norm
    assert overlap == set(), f"Benchmark normalized SHA overlap: {overlap}"


# --------------------------------------------------------------------------
# 6. Split Leakage Isolation
# --------------------------------------------------------------------------


def test_splits_are_source_disjoint(mmim_splits):
    train_sources = {e.input.source_id for e in mmim_splits["train"]}
    val_sources = {e.input.source_id for e in mmim_splits["validation"]}
    test_sources = {e.input.source_id for e in mmim_splits["test"]}

    assert train_sources & val_sources == set()
    assert train_sources & test_sources == set()
    assert val_sources & test_sources == set()


def test_leakage_detector_reports_no_errors(mmim_splits):
    report = detect_leakage(
        train=mmim_splits["train"],
        validation=mmim_splits["validation"],
        test=mmim_splits["test"],
    )
    assert report.ok is True
    assert report.error_count == 0


def test_split_counts_and_tasks(mmim_splits, mmim_all_examples):
    total = len(mmim_all_examples)
    train_count = len(mmim_splits["train"])
    val_count = len(mmim_splits["validation"])
    test_count = len(mmim_splits["test"])

    assert train_count + val_count + test_count == total
    assert train_count > 0
    assert val_count > 0
    assert test_count > 0
