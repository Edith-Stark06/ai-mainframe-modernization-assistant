"""
Load / build / freeze the immutable Phase 6 benchmark (#119).

* :func:`load_benchmark` — read ``data/benchmark/<version>/`` and verify
  its content hash. Any post-freeze mutation makes the load fail loudly.
* :func:`build_benchmark_examples` — construct the ``benchmark-v1``
  examples from the controlled corpus + hand-authored rubrics. This is
  run ONCE by ``scripts/benchmark/freeze_benchmark.py``; it is not part
  of dataset generation.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.benchmark.models import BenchmarkExample, BenchmarkSuite, compute_content_hash
from app.dataset.corpus import REPO_ROOT
from app.dataset.version import ANALYSIS_VERSION, BENCHMARK_VERSION, PROMPT_VERSION

__all__ = [
    "BENCHMARK_DIR",
    "load_benchmark",
    "load_benchmark_examples_file",
    "write_frozen_benchmark",
]

BENCHMARK_DIR = REPO_ROOT / "data" / "benchmark"


def _version_dir(version: str) -> Path:
    return BENCHMARK_DIR / version


def load_benchmark_examples_file(path: str | Path) -> list[BenchmarkExample]:
    out: list[BenchmarkExample] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(BenchmarkExample.model_validate_json(line))
    return out


def load_benchmark(version: str = BENCHMARK_VERSION) -> BenchmarkSuite:
    """Load and hash-verify a frozen benchmark."""
    vdir = _version_dir(version)
    examples_path = vdir / "examples.jsonl"
    manifest_path = vdir / "MANIFEST.json"
    if not examples_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(
            f"frozen benchmark {version} not found under {vdir} — "
            f"run scripts/benchmark/freeze_benchmark.py"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    examples = load_benchmark_examples_file(examples_path)
    return BenchmarkSuite(
        benchmark_version=version,
        prompt_version=manifest["prompt_version"],
        analysis_version=manifest["analysis_version"],
        content_hash=manifest["content_hash"],
        examples=tuple(examples),
    )


def write_frozen_benchmark(
    examples: list[BenchmarkExample],
    version: str = BENCHMARK_VERSION,
    *,
    overwrite: bool = False,
) -> Path:
    """
    Write ``data/benchmark/<version>/`` — refuses to overwrite an existing
    frozen benchmark unless ``overwrite=True`` (which the freeze script
    only passes on an explicit ``--force``).
    """
    vdir = _version_dir(version)
    examples_path = vdir / "examples.jsonl"
    if examples_path.exists() and not overwrite:
        raise FileExistsError(
            f"{examples_path} already exists — a frozen benchmark is immutable. "
            f"Bump BENCHMARK_VERSION or pass --force."
        )
    vdir.mkdir(parents=True, exist_ok=True)

    ordered = sorted(examples, key=lambda e: e.example_id)
    chash = compute_content_hash(ordered)
    with examples_path.open("w", encoding="utf-8", newline="\n") as fh:
        for e in ordered:
            d = e.model_dump(mode="json")
            fh.write(json.dumps(d, sort_keys=True, separators=(",", ":")))
            fh.write("\n")

    manifest = {
        "benchmark_version": version,
        "prompt_version": PROMPT_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "content_hash": chash,
        "example_count": len(ordered),
        "difficulty_distribution": _dist(ordered, lambda e: e.difficulty.value),
        "task_distribution": _dist(ordered, lambda e: e.task_type.value),
        "frozen": True,
        "note": (
            "This benchmark is IMMUTABLE and is NEVER used as training data. "
            "It is not regenerated during dataset builds. Any change requires "
            "a new BENCHMARK_VERSION."
        ),
    }
    (vdir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return vdir


def _dist(examples, keyfn) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in examples:
        out[keyfn(e)] = out.get(keyfn(e), 0) + 1
    return dict(sorted(out.items()))
