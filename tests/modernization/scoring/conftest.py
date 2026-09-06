"""Shared helpers for the Phase 5 scoring regression suite (#117)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.models import AnalysisResult
from app.analysis.service import AnalysisService
from app.modernization.scoring.confidence_aware import (
    ConfidenceAwareScore,
    score_with_confidence,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "phase5"

PHASE5_FIXTURES = (
    "trivial",
    "simple_procedural",
    "complex_procedural",
    "file_processing",
    "highly_coupled",
    "low_complexity",
    "unsupported_syntax",
    "incomplete_parsing",
    "parser_failure",
)


def fixture_path(name: str) -> Path:
    return _FIXTURE_DIR / f"{name}.cbl"


def analyze_fixture(name: str) -> AnalysisResult:
    return AnalysisService().analyze_file(fixture_path(name))


def score_fixture(name: str) -> ConfidenceAwareScore:
    return score_with_confidence(analyze_fixture(name))


def analyze_source(
    source: str, tmp_path: Path, name: str = "prog.cbl"
) -> AnalysisResult:
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(p)


@pytest.fixture(scope="session")
def scores() -> dict[str, ConfidenceAwareScore]:
    """All nine Phase 5 fixtures scored once, keyed by fixture name."""
    return {name: score_fixture(name) for name in PHASE5_FIXTURES}
