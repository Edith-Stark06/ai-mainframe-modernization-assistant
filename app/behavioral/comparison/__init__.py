"""#131 — COBOL vs Java behavioral comparison."""

from __future__ import annotations

from app.behavioral.comparison.comparator import compare_observation
from app.behavioral.comparison.models import (
    ArtifactVersions,
    BehavioralComparison,
    ComparisonStatus,
    Difference,
    OverallStatus,
    Phase10Report,
)
from app.behavioral.comparison.normalize import (
    normalize_line_endings,
    normalize_trailing_line_whitespace,
    try_parse_exact_integer,
    values_equal,
)
from app.behavioral.comparison.report import aggregate_report

__all__ = [
    "compare_observation",
    "aggregate_report",
    "ArtifactVersions",
    "BehavioralComparison",
    "ComparisonStatus",
    "Difference",
    "OverallStatus",
    "Phase10Report",
    "normalize_line_endings",
    "normalize_trailing_line_whitespace",
    "try_parse_exact_integer",
    "values_equal",
]
