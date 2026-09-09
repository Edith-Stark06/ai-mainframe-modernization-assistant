"""#121 Part 15 — dataset integrity & benchmark isolation.

* ``phase6-v1`` (``DV``) is the ORIGINAL build whose training corpus
  overlaps the #119 benchmark — the leakage guard must still reject it.
* ``phase6-v2`` (``DV2``) is the benchmark-disjoint rebuild — the guard
  must accept it at the normal ``min_training_sources`` threshold.
"""

from __future__ import annotations

import pytest

from app.dataset.io import read_examples
from app.training.dataset import (
    DEFAULT_MIN_TRAINING_SOURCES,
    assert_no_benchmark_overlap,
    dataset_dir,
    dataset_manifest_hash,
    resolve_training_data,
)
from app.training.errors import BenchmarkLeakageError, DatasetResolutionError

DV = "phase6-v1"
DV2 = "phase6-v2"
BV = "benchmark-v1"


def test_default_guard_rejects_because_dataset_overlaps_benchmark() -> None:
    with pytest.raises(BenchmarkLeakageError) as exc:
        resolve_training_data(DV, "train", benchmark_version=BV)
    msg = str(exc.value)
    assert "benchmark" in msg and "disjoint" in msg


def test_v2_resolves_at_the_normal_threshold_with_no_exclusions() -> None:
    data = resolve_training_data(DV2, "train", benchmark_version=BV)
    assert data.source_count >= DEFAULT_MIN_TRAINING_SOURCES
    assert data.excluded_benchmark_sources == ()  # nothing to exclude
    assert data.example_count == len(data.records) > 0
    assert_no_benchmark_overlap(list(data.examples), BV)


def test_v2_full_dataset_has_no_benchmark_overlap() -> None:
    everything = read_examples(dataset_dir(DV2) / "all.jsonl")
    assert_no_benchmark_overlap(everything, BV)  # must not raise


def test_v2_metadata_records_version_split_and_hash() -> None:
    data = resolve_training_data(DV2, "train", benchmark_version=BV)
    meta = data.metadata()
    assert meta["dataset_version"] == DV2
    assert meta["training_split"] == "train"
    assert meta["split_seed"] == 20260906
    assert data.dataset_manifest_hash == dataset_manifest_hash(DV2)
    assert dataset_manifest_hash(DV2) != dataset_manifest_hash(DV)


def test_dry_run_lever_yields_a_benchmark_disjoint_slice() -> None:
    data = resolve_training_data(
        DV, "train", benchmark_version=BV, min_training_sources=1
    )
    # every excluded source really is in the benchmark; every kept one is not
    assert data.excluded_benchmark_sources
    assert_no_benchmark_overlap(list(data.examples), BV)
    assert data.split == "train"
    assert data.example_count == len(data.records)
    assert data.dataset_manifest_hash == dataset_manifest_hash(DV)


def test_hash_mismatch_is_rejected() -> None:
    with pytest.raises(DatasetResolutionError, match="hash mismatch"):
        resolve_training_data(
            DV,
            "train",
            benchmark_version=BV,
            expected_manifest_hash="deadbeef" * 8,
            min_training_sources=1,
        )


def test_unknown_dataset_does_not_fall_back() -> None:
    with pytest.raises(DatasetResolutionError, match="not found"):
        resolve_training_data("phase6-vX", "train", benchmark_version=BV)


def test_unknown_split_is_rejected() -> None:
    with pytest.raises(DatasetResolutionError):
        resolve_training_data(
            DV, "holdout", benchmark_version=BV, min_training_sources=1
        )


def test_resolved_metadata_records_split_and_seed() -> None:
    data = resolve_training_data(
        DV, "train", benchmark_version=BV, min_training_sources=1
    )
    meta = data.metadata()
    assert meta["training_split"] == "train"
    assert meta["split_seed"] == 20260906
    assert meta["dataset_version"] == DV
    assert meta["benchmark_version"] == BV
    assert set(meta["excluded_benchmark_sources"]).isdisjoint(meta["source_ids"])


def test_assert_no_benchmark_overlap_flags_full_dataset() -> None:
    everything = read_examples(dataset_dir(DV) / "all.jsonl")
    with pytest.raises(BenchmarkLeakageError):
        assert_no_benchmark_overlap(everything, BV)


def test_max_examples_is_respected() -> None:
    data = resolve_training_data(
        DV, "train", benchmark_version=BV, min_training_sources=1, max_examples=3
    )
    assert data.example_count == 3
