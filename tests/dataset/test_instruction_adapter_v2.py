"""Tests for the MMIM-v2 instruction format adapter.

Mirrors ``tests/dataset/test_instruction_adapter.py`` (mmim-v1, untouched)
but converts the mmim-v2 structured dataset
(``tests/dataset/test_mmim_v2_dataset.py`` generates it if missing) into
instruction-tuning splits under ``data/dataset/mmim-v2/instruction/``.

Also regression-tests the TRANSFORMATION_PLANNING extraction fix: the
architecture ``expected_output`` shape is ``components`` (each tagged with
a ``type`` of DTO/SERVICE/REPOSITORY/...) plus a ``by_type`` count map —
there is no top-level ``dtos``/``services``/``repositories`` key. The
adapter must derive the instruction target from ``components``, not from
those (always-absent) keys, or every transformation_planning example is
silently trained as an empty architecture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.benchmark.suite import load_benchmark
from app.dataset.instruction_adapter import (
    InstructionExample,
    build_instruction_dataset,
    convert_dataset,
    convert_example,
)
from app.dataset.io import read_examples
from app.dataset.schema import GroundTruthStatus, TaskType
from app.dataset.version import BENCHMARK_VERSION, MMIM_DATASET_VERSION_V2

DATASET_DIR = Path("data/dataset/mmim-v2")
INSTRUCTION_DIR = DATASET_DIR / "instruction"


def _ensure_v2_dataset_built() -> None:
    if (DATASET_DIR / "all.jsonl").exists():
        return
    from app.dataset.corpus import load_training_corpus
    from app.dataset.mmim_builder import build_mmim_dataset
    from app.dataset.version import MMIM_GENERATOR_VERSION_V23

    build_mmim_dataset(
        DATASET_DIR,
        load_training_corpus(),
        seed=42,
        dataset_version=MMIM_DATASET_VERSION_V2,
        generator_version=MMIM_GENERATOR_VERSION_V23,
        strict_eligibility=True,
    )


@pytest.fixture(scope="module")
def raw_examples():
    _ensure_v2_dataset_built()
    return read_examples(DATASET_DIR / "all.jsonl")


@pytest.fixture(scope="module")
def instruction_splits(raw_examples):
    if not (INSTRUCTION_DIR / "manifest.json").exists():
        build_instruction_dataset(DATASET_DIR, INSTRUCTION_DIR)

    def _read_inst(path: Path) -> list[InstructionExample]:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [
            InstructionExample.model_validate(json.loads(line))
            for line in lines
            if line.strip()
        ]

    return {
        "train": _read_inst(INSTRUCTION_DIR / "train.jsonl"),
        "validation": _read_inst(INSTRUCTION_DIR / "validation.jsonl"),
        "test": _read_inst(INSTRUCTION_DIR / "test.jsonl"),
    }


@pytest.fixture(scope="module")
def benchmark():
    return load_benchmark(BENCHMARK_VERSION)


# --------------------------------------------------------------------------
# 1. Conversion & schema conformance
# --------------------------------------------------------------------------


def test_every_example_converts_successfully(raw_examples):
    assert len(raw_examples) == 351
    converted = convert_dataset(raw_examples)
    assert len(converted) == len(raw_examples)


def test_valid_message_structure_and_roles(raw_examples):
    for ex in convert_dataset(raw_examples):
        assert len(ex.messages) == 2
        assert ex.messages[0].role == "user"
        assert ex.messages[1].role == "assistant"
        assert len(ex.messages[0].content.strip()) > 0
        assert len(ex.messages[1].content.strip()) > 0


def test_preserves_provenance_and_metadata(raw_examples):
    for raw in raw_examples:
        inst = convert_example(raw)
        assert inst.id == raw.example_id
        assert inst.task == raw.task_type.value
        assert inst.metadata.source_id == raw.input.source_id
        assert inst.metadata.source_sha256 == raw.metadata.source_sha256
        assert inst.metadata.dataset_version == MMIM_DATASET_VERSION_V2
        assert (
            inst.metadata.ground_truth_status == raw.metadata.ground_truth_status.value
        )


def test_assistant_response_is_valid_json(raw_examples):
    for raw in raw_examples:
        parsed = json.loads(convert_example(raw).messages[1].content)
        assert isinstance(parsed, dict)


# --------------------------------------------------------------------------
# 2. TRANSFORMATION_PLANNING extraction correctness (regression)
# --------------------------------------------------------------------------


def test_transformation_planning_target_reflects_real_architecture(raw_examples):
    tp_examples = [
        e for e in raw_examples if e.task_type == TaskType.TRANSFORMATION_PLANNING
    ]
    assert len(tp_examples) == 45

    any_non_empty_dto_or_service = False
    for raw in tp_examples:
        # ground truth itself must have real components (builder-level gate)
        assert raw.expected_output.get("components")

        inst = convert_example(raw)
        parsed = json.loads(inst.messages[1].content)
        assert set(parsed.keys()) == {
            "target_package",
            "dtos",
            "services",
            "repositories",
            "component_counts_by_type",
            "source_mappings",
        }
        if parsed["dtos"] or parsed["services"]:
            any_non_empty_dto_or_service = True
            for comp in parsed["dtos"] + parsed["services"] + parsed["repositories"]:
                assert comp["name"]

    # The whole point of the fix: at least some examples must surface real
    # DTO/SERVICE components, not a uniformly empty structure.
    assert any_non_empty_dto_or_service


# --------------------------------------------------------------------------
# 3. No hidden chain-of-thought
# --------------------------------------------------------------------------


def test_no_hidden_chain_of_thought_fields(raw_examples):
    for raw in raw_examples:
        for msg in convert_example(raw).messages:
            assert "<analysis>" not in msg.content
            assert "</analysis>" not in msg.content
            assert "<thought>" not in msg.content
            assert "</thought>" not in msg.content
            assert "private reasoning" not in msg.content


def test_repair_reasoning_not_generated(raw_examples):
    tasks = {ex.task for ex in convert_dataset(raw_examples)}
    assert TaskType.REPAIR_REASONING.value not in tasks


def test_validation_reasoning_targets_never_empty(raw_examples):
    for raw in raw_examples:
        if raw.task_type == TaskType.VALIDATION_REASONING:
            inst = convert_example(raw)
            parsed = json.loads(inst.messages[1].content)
            assert parsed["test_count"] > 0
            assert parsed["tests"]


# --------------------------------------------------------------------------
# 4. Ground-truth & behavioral safety
# --------------------------------------------------------------------------


def test_ground_truth_status_safety(raw_examples):
    for raw in raw_examples:
        inst = convert_example(raw)
        if inst.task == TaskType.COBOL_TO_JAVA.value:
            if (
                inst.metadata.ground_truth_status
                == GroundTruthStatus.EXECUTABLE_VERIFIED.value
            ):
                parsed = json.loads(inst.messages[1].content)
                assert parsed.get("compiles") is True
                assert "class " in parsed.get("java_code", "")


# --------------------------------------------------------------------------
# 5. Deterministic byte-reproducibility
# --------------------------------------------------------------------------


def test_conversion_is_byte_reproducible(tmp_path, raw_examples):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    manifest1 = build_instruction_dataset(DATASET_DIR, out1)
    manifest2 = build_instruction_dataset(DATASET_DIR, out2)

    assert manifest1 == manifest2
    assert manifest1["dataset_version"] == MMIM_DATASET_VERSION_V2

    for split in ("train.jsonl", "validation.jsonl", "test.jsonl", "manifest.json"):
        assert (out1 / split).read_bytes() == (out2 / split).read_bytes()


# --------------------------------------------------------------------------
# 6. Isolation & zero benchmark leakage
# --------------------------------------------------------------------------


def test_zero_benchmark_leakage_in_instruction_splits(benchmark, instruction_splits):
    bench_ids = {e.input.source_id for e in benchmark.examples}
    for split_name, examples in instruction_splits.items():
        overlap = {ex.metadata.source_id for ex in examples} & bench_ids
        assert overlap == set(), f"benchmark overlap in {split_name}: {overlap}"


def test_split_sources_are_disjoint(instruction_splits):
    train_srcs = {ex.metadata.source_id for ex in instruction_splits["train"]}
    val_srcs = {ex.metadata.source_id for ex in instruction_splits["validation"]}
    test_srcs = {ex.metadata.source_id for ex in instruction_splits["test"]}

    assert train_srcs & val_srcs == set()
    assert train_srcs & test_srcs == set()
    assert val_srcs & test_srcs == set()


def test_token_and_character_sizing(instruction_splits):
    all_exs = (
        instruction_splits["train"]
        + instruction_splits["validation"]
        + instruction_splits["test"]
    )
    for ex in all_exs:
        assert ex.metadata.char_count_user > 0
        assert ex.metadata.char_count_assistant > 0
        assert ex.metadata.estimated_tokens_user > 0
        assert ex.metadata.estimated_tokens_assistant > 0
        assert (
            ex.metadata.estimated_tokens_total
            == ex.metadata.estimated_tokens_user
            + ex.metadata.estimated_tokens_assistant
        )


def test_mmim_v1_instruction_files_untouched():
    v1_manifest = json.loads(
        Path("data/dataset/mmim-v1/instruction/manifest.json").read_text("utf-8")
    )
    assert v1_manifest["dataset_version"] == "mmim-v1"
    assert v1_manifest["example_count"] == 144
