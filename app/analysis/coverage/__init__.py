"""
Analysis Coverage (task #115 — Phase 5).

Multi-dimensional measurement of *how much of a COBOL source file was
actually understood* by the analysis pipeline. See :mod:`.analyzer` and
:mod:`.models`.
"""

from app.analysis.coverage.analyzer import compute_coverage
from app.analysis.coverage.models import (
    CoverageDimension,
    CoverageReport,
    CoverageStatus,
    UnsupportedSyntaxCoverage,
)

__all__ = [
    "CoverageDimension",
    "CoverageReport",
    "CoverageStatus",
    "UnsupportedSyntaxCoverage",
    "compute_coverage",
]
