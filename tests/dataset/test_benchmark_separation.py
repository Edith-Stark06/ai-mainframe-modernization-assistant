"""Hard regression: the phase6-v2 training dataset and benchmark-v1 are
source-disjoint — by id AND by content hash AND by normalized text.

If this ever fails, a future #121 fine-tuning run would be training on
its own evaluation set. It is an ERROR, never a warning.
"""

from __future__ import annotations

import hashlib

import pytest

from app.benchmark.suite import load_benchmark
from app.dataset.corpus import (
    BENCHMARK_SOURCE_IDS,
    load_evaluation_corpus,
    load_training_corpus,
)
from app.dataset.io import read_examples
from app.dataset.version import BENCHMARK_VERSION, DATASET_VERSION_V2
from app.training.dataset import assert_no_benchmark_overlap, dataset_dir
from app.training.errors import BenchmarkLeakageError

FROZEN_BENCHMARK_HASH = (
    "df0ff3202f54bfaf1dabecb801bbb07506875d78b689d9c641a2dd461aa8a632"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


@pytest.fixture(scope="module")
def benchmark():
    return load_benchmark(BENCHMARK_VERSION)


@pytest.fixture(scope="module")
def v2_examples():
    return read_examples(dataset_dir(DATASET_VERSION_V2) / "all.jsonl")


def test_benchmark_source_ids_constant_matches_frozen_benchmark(benchmark) -> None:
    on_disk = {e.input.source_id for e in benchmark.examples}
    assert on_disk == set(BENCHMARK_SOURCE_IDS)


def test_zero_shared_source_ids(benchmark, v2_examples) -> None:
    train_ids = {e.input.source_id for e in v2_examples}
    bench_ids = {e.input.source_id for e in benchmark.examples}
    assert train_ids & bench_ids == set()


def test_zero_shared_source_hashes(benchmark, v2_examples) -> None:
    train_sha = {_sha(e.input.source) for e in v2_examples}
    bench_sha = {_sha(e.input.source) for e in benchmark.examples}
    assert train_sha & bench_sha == set()


def test_zero_shared_normalized_sources(benchmark, v2_examples) -> None:
    train_n = {_sha(_norm(e.input.source)) for e in v2_examples}
    bench_n = {_sha(_norm(e.input.source)) for e in benchmark.examples}
    assert train_n & bench_n == set()


def test_every_training_example_is_outside_the_benchmark(
    benchmark, v2_examples
) -> None:
    bench_ids = {e.input.source_id for e in benchmark.examples}
    for ex in v2_examples:
        assert ex.input.source_id not in bench_ids


def test_121_guard_would_flag_an_injected_benchmark_source(v2_examples) -> None:
    from tests.dataset.conftest import make_example

    bench_rec = load_evaluation_corpus()[0]
    # inject one training example whose source IS a benchmark program
    poisoned = [
        make_example(source=bench_rec.source, source_id=bench_rec.source_id),
        *v2_examples,
    ]
    with pytest.raises(BenchmarkLeakageError):
        assert_no_benchmark_overlap(poisoned, BENCHMARK_VERSION)


def test_benchmark_content_hash_is_unchanged(benchmark) -> None:
    assert benchmark.content_hash == FROZEN_BENCHMARK_HASH


def test_training_and_evaluation_corpora_are_disjoint() -> None:
    t = {r.source_id for r in load_training_corpus()}
    e = {r.source_id for r in load_evaluation_corpus()}
    assert t & e == set()
    assert e == set(BENCHMARK_SOURCE_IDS)
