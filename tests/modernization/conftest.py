"""Shared helpers for Phase 4 (Modernization Intelligence) tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.models import AnalysisResult
from app.analysis.service import AnalysisService

_COMPLEX_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "workspace"
    / "2e87036d-b90e-488f-b199-3162eb7c1c7e"
    / "complex_acctbatch.cbl"
)

_ELIGIBILITY_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "phase4"
    / "eligibility_rules.cbl"
)


def analyze_source(
    source: str, tmp_path: Path, name: str = "prog.cbl"
) -> AnalysisResult:
    """Run the real Phase 1–3 pipeline over *source* and return the result."""
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


@pytest.fixture
def analyze(tmp_path):
    """Fixture form of :func:`analyze_source` bound to the test's tmp_path."""

    def _run(source: str, name: str = "prog.cbl") -> AnalysisResult:
        return analyze_source(source, tmp_path, name)

    return _run


@pytest.fixture(scope="session")
def complex_analysis() -> AnalysisResult:
    """The shared ~500-line complex fixture used across Phases 1–3."""
    return AnalysisService().analyze_file(_COMPLEX_FIXTURE)


@pytest.fixture(scope="session")
def eligibility_analysis() -> AnalysisResult:
    """A realistic multi-rule fixture added for Phase 4."""
    return AnalysisService().analyze_file(_ELIGIBILITY_FIXTURE)
