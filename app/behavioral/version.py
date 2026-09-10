"""
Phase 10 versioning (#129-#131).

Every behavioral artifact records the versions that produced it, and a
:class:`~app.behavioral.comparison.models.BehavioralComparison` pins the
exact COBOL source hash, Java project hash, architecture hash and test
case hash it was computed from — comparisons across different generated
versions must never be mixed silently.
"""

from __future__ import annotations

from app.dataset.version import ANALYSIS_VERSION

EXTRACTION_VERSION: str = "p10-extract-v1"
JAVA_TEST_VERSION: str = "p10-javatest-v1"
COMPARISON_VERSION: str = "p10-compare-v1"
ANALYSIS_CONTRACT_VERSION: str = ANALYSIS_VERSION

__all__ = [
    "EXTRACTION_VERSION",
    "JAVA_TEST_VERSION",
    "COMPARISON_VERSION",
    "ANALYSIS_CONTRACT_VERSION",
]
