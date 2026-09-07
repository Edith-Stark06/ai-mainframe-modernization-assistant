"""
Deterministic train / validation / test splitting (#118 §9).

The split is reproducible from ``(dataset_version, seed)`` alone — never a
per-run random shuffle.

**Source-group separation is enforced**: every example derived from the
same COBOL program (``input.source_id``) is assigned to exactly one
split, so no program's analysis can appear in both train and test.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.dataset.schema import DatasetExample

__all__ = ["SplitRatios", "SplitResult", "split_dataset"]

_BUCKETS = 10_000


@dataclass(frozen=True)
class SplitRatios:
    train: float = 0.70
    validation: float = 0.15
    test: float = 0.15

    def __post_init__(self) -> None:
        total = self.train + self.validation + self.test
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"split ratios must sum to 1.0, got {total}")
        for name, v in (
            ("train", self.train),
            ("validation", self.validation),
            ("test", self.test),
        ):
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} ratio out of range: {v}")


@dataclass
class SplitResult:
    train: list[DatasetExample] = field(default_factory=list)
    validation: list[DatasetExample] = field(default_factory=list)
    test: list[DatasetExample] = field(default_factory=list)
    #: source_id -> split name
    assignment: dict[str, str] = field(default_factory=dict)
    seed: int = 0
    dataset_version: str = ""
    ratios: SplitRatios = field(default_factory=SplitRatios)

    def manifest(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "seed": self.seed,
            "ratios": {
                "train": self.ratios.train,
                "validation": self.ratios.validation,
                "test": self.ratios.test,
            },
            "counts": {
                "train": len(self.train),
                "validation": len(self.validation),
                "test": len(self.test),
            },
            "source_assignment": dict(sorted(self.assignment.items())),
        }


def _bucket(dataset_version: str, seed: int, source_id: str) -> int:
    h = hashlib.sha256(
        f"{dataset_version}\x1f{seed}\x1f{source_id}".encode("utf-8")
    ).hexdigest()
    return int(h, 16) % _BUCKETS


def split_dataset(
    examples: list[DatasetExample],
    seed: int = 0,
    ratios: SplitRatios | None = None,
    dataset_version: str | None = None,
) -> SplitResult:
    """
    Split *examples* into train/validation/test, grouped by source program.

    Args:
        examples: the full dataset.
        seed: reproducibility seed.
        ratios: split proportions (default 70/15/15).
        dataset_version: overrides the version taken from the examples
            (they must all share one).
    """
    ratios = ratios or SplitRatios()
    if not examples:
        return SplitResult(
            seed=seed, ratios=ratios, dataset_version=dataset_version or ""
        )

    versions = {e.dataset_version for e in examples}
    if len(versions) != 1 and dataset_version is None:
        raise ValueError(f"examples span multiple dataset versions: {sorted(versions)}")
    version = dataset_version or next(iter(versions))

    train_cut = int(round(ratios.train * _BUCKETS))
    val_cut = train_cut + int(round(ratios.validation * _BUCKETS))

    assignment: dict[str, str] = {}
    for source_id in sorted({e.input.source_id for e in examples}):
        b = _bucket(version, seed, source_id)
        if b < train_cut:
            assignment[source_id] = "train"
        elif b < val_cut:
            assignment[source_id] = "validation"
        else:
            assignment[source_id] = "test"

    result = SplitResult(
        assignment=assignment, seed=seed, ratios=ratios, dataset_version=version
    )
    ordered = sorted(
        examples, key=lambda e: (e.task_type.value, e.input.source_id, e.example_id)
    )
    for ex in ordered:
        getattr(result, assignment[ex.input.source_id]).append(ex)
    return result
