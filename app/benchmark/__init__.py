"""
Phase 6 — Evaluation Benchmark (#119).

A frozen, immutable, hash-verified set of examples used ONLY to evaluate
models — never as training data. See :mod:`.suite` (load / freeze),
:mod:`.curated` (the benchmark-v1 contents), :mod:`.metrics`,
:mod:`.scoring`, :mod:`.report`.
"""

from app.benchmark.models import BenchmarkExample, BenchmarkSuite
from app.benchmark.report import BenchmarkReport, generate_report
from app.benchmark.scoring import ExampleScore, score_example
from app.benchmark.suite import load_benchmark

__all__ = [
    "BenchmarkExample",
    "BenchmarkSuite",
    "BenchmarkReport",
    "ExampleScore",
    "generate_report",
    "score_example",
    "load_benchmark",
]
