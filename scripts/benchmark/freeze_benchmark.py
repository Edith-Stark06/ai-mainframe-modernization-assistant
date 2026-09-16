"""
Freeze the immutable Phase 6 evaluation benchmark (#119).

    python -m scripts.benchmark.freeze_benchmark [--force]

Builds ``benchmark-v1`` from the controlled corpus + curated rubrics and
writes ``data/benchmark/benchmark-v1/`` (examples.jsonl + MANIFEST.json
with a content hash). Refuses to overwrite an existing frozen benchmark
unless ``--force`` is given — bump ``BENCHMARK_VERSION`` instead.

The benchmark is NEVER used as training data.
"""

from __future__ import annotations

import argparse
import sys

from app.benchmark.curated import build_benchmark_examples
from app.benchmark.suite import load_benchmark, write_frozen_benchmark
from app.dataset.version import BENCHMARK_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    examples = build_benchmark_examples()
    print(f"built {len(examples)} benchmark example(s)")

    vdir = write_frozen_benchmark(examples, BENCHMARK_VERSION, overwrite=args.force)
    print(f"wrote {vdir}")

    suite = load_benchmark(BENCHMARK_VERSION)  # verifies the hash
    print(f"content hash: {suite.content_hash}")
    dist = {}
    for e in suite.examples:
        dist[e.difficulty.value] = dist.get(e.difficulty.value, 0) + 1
    print(f"difficulty distribution: {dict(sorted(dist.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
