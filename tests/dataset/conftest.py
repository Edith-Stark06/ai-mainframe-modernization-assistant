"""Shared helpers for Phase 6 dataset tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.dataset.builder import DatasetBuilder
from app.dataset.corpus import load_phase6_corpus
from app.dataset.io import read_examples, write_jsonl
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


# ---------------------------------------------------------------------------
# Regenerable split files
#
# .gitignore deliberately excludes ``data/dataset/*/train.jsonl`` and
# ``validation.jsonl`` ("regenerable dataset splits (derive from all.jsonl +
# split_manifest.json)") while tracking ``all.jsonl``, ``split_manifest.json``
# and ``test.jsonl``. Several dataset tests read the ignored files directly, so
# on a fresh checkout they errored with FileNotFoundError. This fixture derives
# any *missing* split file exactly as the builder wrote it (the derivation is
# verified byte-identical, and ``test_split_regeneration.py`` keeps it honest);
# it never overwrites a file that already exists.
# ---------------------------------------------------------------------------

_DATASET_ROOT = Path(__file__).resolve().parents[2] / "data" / "dataset"
_REGENERABLE = ("mmim-v1", "mmim-v2")


def derive_splits(dataset_dir: Path) -> dict[str, list]:
    """Return ``{split: examples}`` derived from ``all.jsonl`` and the
    ``source_assignment`` recorded in ``split_manifest.json``."""
    manifest = json.loads(
        (dataset_dir / "split_manifest.json").read_text(encoding="utf-8")
    )
    assignment = manifest["source_assignment"]
    parts: dict[str, list] = {"train": [], "validation": [], "test": []}
    for example in read_examples(dataset_dir / "all.jsonl"):
        parts[assignment[example.input.source_id]].append(example)
    return parts


@pytest.fixture(scope="session", autouse=True)
def _regenerate_ignored_dataset_splits() -> None:
    for name in _REGENERABLE:
        directory = _DATASET_ROOT / name
        missing = [
            split
            for split in ("train", "validation")
            if not (directory / f"{split}.jsonl").exists()
        ]
        if not missing:
            continue
        if not (
            (directory / "all.jsonl").exists()
            and (directory / "split_manifest.json").exists()
        ):
            continue  # nothing to derive from; the dependent test reports it
        parts = derive_splits(directory)
        for split in missing:
            write_jsonl(directory / f"{split}.jsonl", parts[split])
