"""
Phase 6 evaluation benchmark models (#119).

The benchmark is a **frozen, immutable** set of examples that is NEVER
used as training data. That separation is enforced here and in
:mod:`app.benchmark.suite`:

* every :class:`BenchmarkExample` carries ``never_training = True``;
* the on-disk benchmark (``data/benchmark/<version>/``) is content-hashed
  in its ``MANIFEST.json`` and :meth:`BenchmarkSuite.load` verifies the
  hash;
* the dataset builder (#118) does not read or write the benchmark
  directory.

Difficulty is a graded, defined property — not an arbitrary label:

* ``easy``        — one paragraph, few statements, no CALL, no loop,
  fully covered by deterministic analysis.
* ``medium``      — several paragraphs / a PERFORM / at least one IF /
  at most one CALL, fully covered.
* ``difficult``   — nested control flow, PERFORM UNTIL, multiple CALLs
  or cross-paragraph shared state, fully covered.
* ``adversarial`` — designed to expose a specific failure: a misleading
  identifier, a misleading comment, unsupported syntax, incomplete
  parsing, or a question whose honest answer is "not determinable from
  the source". Each adversarial example records its ``trap``.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.dataset.schema import (
    Difficulty,
    ExampleAnalysis,
    ExampleInput,
    SourceLocation,
    TaskType,
)

__all__ = ["BenchmarkExample", "BenchmarkSuite"]


class BenchmarkExample(BaseModel):
    """One frozen benchmark item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    example_id: str = Field(..., min_length=1)
    benchmark_version: str = Field(..., min_length=1)
    task_type: TaskType
    difficulty: Difficulty
    never_training: bool = Field(default=True)

    input: ExampleInput
    analysis: ExampleAnalysis = Field(default_factory=ExampleAnalysis)
    #: the gold answer used for scoring
    expected_output: dict[str, Any]
    #: source locations the gold answer is grounded in
    source_locations: list[SourceLocation] = Field(default_factory=list)
    #: task-specific scoring parameters (required concepts, expected
    #: strategy, forbidden claims for adversarial, expected rule/risk
    #: sets, …)
    rubric: dict[str, Any] = Field(default_factory=dict)
    #: for adversarial examples only — a short description of the trap
    trap: str | None = None

    @model_validator(mode="after")
    def _never_training(self) -> BenchmarkExample:
        if self.never_training is not True:
            raise ValueError("benchmark examples must have never_training = True")
        return self

    @model_validator(mode="after")
    def _adversarial_has_trap(self) -> BenchmarkExample:
        if self.difficulty is Difficulty.ADVERSARIAL and not (self.trap or "").strip():
            raise ValueError(
                f"adversarial example {self.example_id} must document its trap"
            )
        return self


class BenchmarkSuite(BaseModel):
    """An ordered, hash-verified collection of benchmark examples."""

    model_config = ConfigDict(frozen=True)

    benchmark_version: str
    prompt_version: str
    analysis_version: str
    content_hash: str
    examples: tuple[BenchmarkExample, ...]

    @model_validator(mode="after")
    def _consistent_and_hashed(self) -> BenchmarkSuite:
        ids = [e.example_id for e in self.examples]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate benchmark example_id")
        if any(e.benchmark_version != self.benchmark_version for e in self.examples):
            raise ValueError("example benchmark_version mismatch")
        expected = compute_content_hash(self.examples)
        if self.content_hash and self.content_hash != expected:
            raise ValueError(
                f"benchmark content hash mismatch: manifest {self.content_hash} "
                f"!= computed {expected} — the benchmark has been mutated"
            )
        return self

    def by_task(self) -> dict[TaskType, list[BenchmarkExample]]:
        out: dict[TaskType, list[BenchmarkExample]] = {}
        for e in self.examples:
            out.setdefault(e.task_type, []).append(e)
        return out

    def by_difficulty(self) -> dict[Difficulty, list[BenchmarkExample]]:
        out: dict[Difficulty, list[BenchmarkExample]] = {}
        for e in self.examples:
            out.setdefault(e.difficulty, []).append(e)
        return out


def compute_content_hash(
    examples: tuple[BenchmarkExample, ...] | list[BenchmarkExample],
) -> str:
    """Deterministic hash over the ordered example contents (excl. version)."""
    import json

    parts = []
    for e in examples:
        d = e.model_dump(mode="json")
        d.pop("benchmark_version", None)
        parts.append(json.dumps(d, sort_keys=True, separators=(",", ":")))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
