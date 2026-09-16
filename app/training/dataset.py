"""
Training-data resolution + benchmark isolation (#121 Parts 4 & "Strict
Data Separation").

``resolve_training_data`` is the *only* way the fine-tuning pipeline gets
examples. It:

1. locates ``data/dataset/<dataset_version>/`` (Phase 6 / #118);
2. hashes ``all.jsonl`` and, if an expected hash was supplied, fails on
   mismatch — never silently using a different dataset;
3. reconstructs the requested split deterministically from
   ``split_manifest.json`` (``seed``) + :func:`app.dataset.splitting.split_dataset`
   — so it does not depend on the git-ignored ``train.jsonl``;
4. re-validates every example against the Phase 6 schema;
5. **removes every source that also appears in the frozen #119
   benchmark** and refuses to proceed if too little training data
   remains.

The benchmark is loaded read-only (and hash-verified by
``load_benchmark``); nothing under ``data/benchmark/`` is written.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.benchmark.suite import load_benchmark
from app.dataset.corpus import REPO_ROOT
from app.dataset.io import read_examples
from app.dataset.schema import DatasetExample
from app.dataset.splitting import split_dataset
from app.training.errors import BenchmarkLeakageError, DatasetResolutionError
from app.training.version import PREPROCESSING_VERSION

__all__ = [
    "TrainingRecord",
    "ResolvedTrainingData",
    "dataset_dir",
    "dataset_manifest_hash",
    "benchmark_source_fingerprint",
    "assert_no_benchmark_overlap",
    "resolve_training_data",
]

DATASET_ROOT = REPO_ROOT / "data" / "dataset"

#: A benchmark-safe training split must retain at least this many
#: distinct source programs to be worth training on. Below this the
#: pipeline raises rather than produce a meaningless run.
DEFAULT_MIN_TRAINING_SOURCES = 8


def _normalize_source(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrainingRecord:
    """One prompt/response pair fed to the training backend."""

    example_id: str
    source_id: str
    task_type: str
    prompt: str
    response: str

    def to_dict(self) -> dict[str, str]:
        return {
            "example_id": self.example_id,
            "source_id": self.source_id,
            "task_type": self.task_type,
            "prompt": self.prompt,
            "response": self.response,
        }


@dataclass(frozen=True)
class ResolvedTrainingData:
    """The immutable result of :func:`resolve_training_data`."""

    dataset_version: str
    dataset_manifest_hash: str
    split: str
    seed: int
    preprocessing_version: str
    examples: tuple[DatasetExample, ...]
    records: tuple[TrainingRecord, ...]
    source_ids: tuple[str, ...]
    excluded_benchmark_sources: tuple[str, ...]
    benchmark_version: str
    benchmark_content_hash: str

    @property
    def example_count(self) -> int:
        return len(self.records)

    @property
    def source_count(self) -> int:
        return len(self.source_ids)

    def metadata(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "training_split": self.split,
            "split_seed": self.seed,
            "preprocessing_version": self.preprocessing_version,
            "example_count": self.example_count,
            "source_count": self.source_count,
            "source_ids": list(self.source_ids),
            "excluded_benchmark_sources": list(self.excluded_benchmark_sources),
            "benchmark_version": self.benchmark_version,
            "benchmark_content_hash": self.benchmark_content_hash,
        }


# ---------------------------------------------------------------------------
# hashing / discovery
# ---------------------------------------------------------------------------


def dataset_dir(dataset_version: str) -> Path:
    return DATASET_ROOT / dataset_version


def _canonical_bytes(path: Path) -> bytes:
    """Read *path* as its canonical LF representation.

    The committed dataset artifacts are LF (enforced by ``.gitattributes``
    ``data/**/*.jsonl text eol=lf``), so on a correct checkout this is a
    no-op. The ``\\r\\n`` -> ``\\n`` fold is defence-in-depth for a working
    copy cloned before that policy existed (or with a global core.autocrlf
    override): it makes ``dataset_manifest_hash`` return the *canonical*
    hash — the one committed and pinned in the training configs — instead
    of a platform-dependent one. It cannot hide a real content change:
    canonical JSONL lines never contain ``\\r``, so any genuine byte
    difference still changes the hash.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def dataset_manifest_hash(dataset_version: str) -> str:
    """sha256 of the canonical (LF) ``all.jsonl`` for *dataset_version*."""
    path = dataset_dir(dataset_version) / "all.jsonl"
    if not path.exists():
        raise DatasetResolutionError(
            f"dataset {dataset_version!r} not found — expected {path}"
        )
    return hashlib.sha256(_canonical_bytes(path)).hexdigest()


def benchmark_source_fingerprint(benchmark_version: str) -> tuple[set[str], set[str]]:
    """``(source_ids, normalized source texts)`` present in the benchmark."""
    suite = load_benchmark(benchmark_version)
    ids = {e.input.source_id for e in suite.examples}
    texts = {_normalize_source(e.input.source) for e in suite.examples}
    return ids, texts


def assert_no_benchmark_overlap(
    examples: list[DatasetExample], benchmark_version: str
) -> None:
    """Raise :class:`BenchmarkLeakageError` if *examples* touch the benchmark."""
    b_ids, b_texts = benchmark_source_fingerprint(benchmark_version)
    bad_ids = sorted({e.input.source_id for e in examples} & b_ids)
    bad_texts = sorted(
        {
            e.input.source_id
            for e in examples
            if _normalize_source(e.input.source) in b_texts
        }
    )
    offending = sorted(set(bad_ids) | set(bad_texts))
    if offending:
        raise BenchmarkLeakageError(
            f"{len(offending)} training source(s) also appear in benchmark "
            f"{benchmark_version!r}: {offending}. Training data and the frozen "
            f"evaluation benchmark must be disjoint."
        )


# ---------------------------------------------------------------------------
# preprocessing
# ---------------------------------------------------------------------------


def _render_record(ex: DatasetExample) -> TrainingRecord:
    """Deterministically turn a #118 example into a prompt/response pair.

    Versioned by ``PREPROCESSING_VERSION``. This is intentionally simple
    and self-contained — the *evaluation* prompt (``p6-prompt-v1``) is a
    separate concern owned by Phase 6.
    """
    import json

    ctx = ex.input.context or {}
    question = str(ctx.get("question", "")).strip()
    parts = [
        f"## Task\n{ex.task_type.value}",
        f"## Source: {ex.input.source_id}\n```cobol\n{ex.input.source.strip()}\n```",
    ]
    if question:
        parts.append(f"## Question\n{question}")
    prompt = "\n\n".join(parts) + "\n"
    response = json.dumps(ex.expected_output, sort_keys=True, ensure_ascii=False)
    return TrainingRecord(
        example_id=ex.example_id,
        source_id=ex.input.source_id,
        task_type=ex.task_type.value,
        prompt=prompt,
        response=response,
    )


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


def _load_split_manifest(dataset_version: str) -> dict[str, Any]:
    import json

    path = dataset_dir(dataset_version) / "split_manifest.json"
    if not path.exists():
        raise DatasetResolutionError(f"split manifest not found — expected {path}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def resolve_training_data(
    dataset_version: str,
    split: str = "train",
    *,
    benchmark_version: str,
    expected_manifest_hash: str | None = None,
    min_training_sources: int = DEFAULT_MIN_TRAINING_SOURCES,
    max_examples: int | None = None,
) -> ResolvedTrainingData:
    """Resolve and benchmark-isolate a training split.

    Raises
    ------
    DatasetResolutionError
        dataset / split missing, hash mismatch, or a malformed example.
    BenchmarkLeakageError
        the benchmark-safe split is too small to train on.
    """
    if split not in ("train", "validation", "test"):
        raise DatasetResolutionError(f"unknown split {split!r}")

    ddir = dataset_dir(dataset_version)
    all_path = ddir / "all.jsonl"
    if not all_path.exists():
        raise DatasetResolutionError(
            f"dataset {dataset_version!r} not found — expected {all_path}. "
            f"The pipeline does not fall back to another dataset."
        )

    manifest_hash = hashlib.sha256(_canonical_bytes(all_path)).hexdigest()
    if expected_manifest_hash and expected_manifest_hash != manifest_hash:
        raise DatasetResolutionError(
            f"dataset hash mismatch for {dataset_version!r}: "
            f"expected {expected_manifest_hash}, on disk {manifest_hash}"
        )

    try:
        examples = read_examples(all_path)
    except Exception as exc:  # malformed line / schema failure
        raise DatasetResolutionError(
            f"{all_path} contains an example that fails Phase 6 validation: {exc}"
        ) from exc
    if not examples:
        raise DatasetResolutionError(f"{all_path} is empty")

    split_manifest = _load_split_manifest(dataset_version)
    seed = int(split_manifest.get("seed", 0))
    recorded_assignment = split_manifest.get("source_assignment", {})

    result = split_dataset(examples, seed=seed, dataset_version=dataset_version)
    if recorded_assignment and result.assignment != recorded_assignment:
        raise DatasetResolutionError(
            "reconstructed split does not match split_manifest.json — the "
            "dataset or splitting logic changed since the split was recorded"
        )
    split_examples: list[DatasetExample] = getattr(result, split)
    if not split_examples:
        raise DatasetResolutionError(
            f"split {split!r} is empty for dataset {dataset_version!r}"
        )

    # --- benchmark isolation --------------------------------------------
    b_ids, b_texts = benchmark_source_fingerprint(benchmark_version)
    suite = load_benchmark(benchmark_version)

    kept: list[DatasetExample] = []
    excluded_sources: set[str] = set()
    for ex in split_examples:
        if ex.input.source_id in b_ids or _normalize_source(ex.input.source) in b_texts:
            excluded_sources.add(ex.input.source_id)
        else:
            kept.append(ex)

    kept_sources = sorted({e.input.source_id for e in kept})
    if len(kept_sources) < min_training_sources:
        raise BenchmarkLeakageError(
            f"after removing {len(excluded_sources)} source(s) shared with "
            f"benchmark {benchmark_version!r}, only {len(kept_sources)} training "
            f"source(s) remain ({kept_sources}) — below the minimum of "
            f"{min_training_sources}. The Phase 6 dataset (#118) and benchmark "
            f"(#119) are drawn from the same corpus; a fine-tuning run needs a "
            f"training corpus that is disjoint from the benchmark. Fix this in "
            f"Phase 6 (hold sources out of the benchmark, or exclude benchmark "
            f"sources from the dataset) before running #121 for real."
        )

    # defensive: prove the kept set really is clean
    assert_no_benchmark_overlap(kept, benchmark_version)

    kept.sort(key=lambda e: (e.task_type.value, e.input.source_id, e.example_id))
    if max_examples is not None:
        kept = kept[:max_examples]
        kept_sources = sorted({e.input.source_id for e in kept})

    records = tuple(_render_record(e) for e in kept)

    return ResolvedTrainingData(
        dataset_version=dataset_version,
        dataset_manifest_hash=manifest_hash,
        split=split,
        seed=seed,
        preprocessing_version=PREPROCESSING_VERSION,
        examples=tuple(kept),
        records=records,
        source_ids=tuple(kept_sources),
        excluded_benchmark_sources=tuple(sorted(excluded_sources)),
        benchmark_version=benchmark_version,
        benchmark_content_hash=suite.content_hash,
    )
