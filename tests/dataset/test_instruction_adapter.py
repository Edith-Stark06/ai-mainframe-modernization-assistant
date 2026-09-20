"""Tests for the MMIM instruction format adapter.

Verifies:
- Complete conversion of DatasetExample records to InstructionExample schema
- Valid conversational roles ('user', 'assistant')
- Strict preservation of provenance (source_id, source_sha256, task_type, ground_truth_status)
- Deterministic byte-reproducibility across runs
- Absence of hidden chain-of-thought (<analysis> private reasoning tags)
- Zero benchmark leakage and preserved split assignments
- Token and character count sizing
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
from app.dataset.version import BENCHMARK_VERSION, MMIM_DATASET_VERSION

DATASET_DIR = Path("data/dataset/mmim-v1")
INSTRUCTION_DIR = DATASET_DIR / "instruction"


@pytest.fixture(scope="module")
def raw_examples():
    return read_examples(DATASET_DIR / "all.jsonl")


@pytest.fixture(scope="module")
def instruction_splits():
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
# 1. Conversion & Schema Conformance
# --------------------------------------------------------------------------


def test_every_example_converts_successfully(raw_examples):
    assert len(raw_examples) == 144
    converted = convert_dataset(raw_examples)
    assert len(converted) == len(raw_examples)


def test_valid_message_structure_and_roles(raw_examples):
    converted = convert_dataset(raw_examples)
    for ex in converted:
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
        assert inst.metadata.dataset_version == MMIM_DATASET_VERSION
        assert (
            inst.metadata.ground_truth_status == raw.metadata.ground_truth_status.value
        )


# --------------------------------------------------------------------------
# 2. No Hidden Chain-of-Thought / Auditable Evidence
# --------------------------------------------------------------------------


def test_no_hidden_chain_of_thought_fields(raw_examples):
    for raw in raw_examples:
        inst = convert_example(raw)
        for msg in inst.messages:
            assert "<analysis>" not in msg.content
            assert "</analysis>" not in msg.content
            assert "<thought>" not in msg.content
            assert "</thought>" not in msg.content
            assert "private reasoning" not in msg.content


def test_repair_reasoning_not_generated(raw_examples):
    converted = convert_dataset(raw_examples)
    tasks = {ex.task for ex in converted}
    assert TaskType.REPAIR_REASONING.value not in tasks


def test_assistant_response_is_valid_json(raw_examples):
    for raw in raw_examples:
        inst = convert_example(raw)
        asst_msg = inst.messages[1].content
        parsed = json.loads(asst_msg)
        assert isinstance(parsed, dict)


# --------------------------------------------------------------------------
# 3. Ground-Truth & Behavioral Safety
# --------------------------------------------------------------------------


def test_ground_truth_status_safety(raw_examples):
    for raw in raw_examples:
        inst = convert_example(raw)
        gt = inst.metadata.ground_truth_status
        if inst.task == TaskType.COBOL_TO_JAVA.value:
            if gt == GroundTruthStatus.EXECUTABLE_VERIFIED.value:
                parsed = json.loads(inst.messages[1].content)
                assert parsed.get("compiles") is True
                assert "class " in parsed.get("java_code", "")


# --------------------------------------------------------------------------
# 4. Deterministic Byte-Reproducibility
# --------------------------------------------------------------------------


def test_conversion_is_byte_reproducible(tmp_path, raw_examples):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    manifest1 = build_instruction_dataset(DATASET_DIR, out1)
    manifest2 = build_instruction_dataset(DATASET_DIR, out2)

    assert manifest1 == manifest2

    for split in ("train.jsonl", "validation.jsonl", "test.jsonl", "manifest.json"):
        bytes1 = (out1 / split).read_bytes()
        bytes2 = (out2 / split).read_bytes()
        assert bytes1 == bytes2, f"Discrepancy in {split}"


# --------------------------------------------------------------------------
# 5. Isolation & Zero Benchmark Leakage
# --------------------------------------------------------------------------


def test_zero_benchmark_leakage_in_instruction_splits(benchmark, instruction_splits):
    bench_ids = {e.input.source_id for e in benchmark.examples}
    for split_name, examples in instruction_splits.items():
        split_sources = {ex.metadata.source_id for ex in examples}
        overlap = split_sources & bench_ids
        assert overlap == set(), f"Benchmark overlap in {split_name}: {overlap}"


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
        # Verify total fits comfortably within standard 8k / 32k context windows
        assert ex.metadata.estimated_tokens_total < 8192
