"""Unit tests for the #116 confidence model and policy."""

from __future__ import annotations

import pytest

from app.analysis.coverage import compute_coverage
from app.analysis.models import AnalysisResult
from app.modernization.scoring.confidence import (
    AnalysisConfidence,
    ConfidenceFactor,
    compute_confidence,
)


def test_confidence_bounds_validated() -> None:
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        AnalysisConfidence(score=1.5)
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        AnalysisConfidence(score=-0.1)


def test_factor_to_dict() -> None:
    f = ConfidenceFactor(name="x", effect=-0.2, reason="r", evidence=("e",))
    assert f.to_dict() == {
        "name": "x",
        "effect": -0.2,
        "reason": "r",
        "evidence": ["e"],
    }


def _result(**over) -> AnalysisResult:
    base = dict(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=False,
        dependencies=[],
        ast=None,
        ir=None,
        coverage=None,
    )
    base.update(over)
    return AnalysisResult(**base)


def test_pipeline_failure_confidence_near_zero() -> None:
    ar = _result()  # no coverage, no ast
    cr = compute_coverage(ar, None, [])
    conf = compute_confidence(cr, ar, None)
    assert conf.score <= 0.10
    assert conf.score >= 0.0


def test_confidence_never_exceeds_coverage_plus_zero() -> None:
    """base == coverage.overall; penalties/ceilings only reduce it."""
    ar = _result()
    cr = compute_coverage(ar, None, [])
    conf = compute_confidence(cr, ar, None)
    assert conf.score <= cr.overall + 1e-9


def test_every_factor_effect_is_non_positive_after_base() -> None:
    ar = _result()
    cr = compute_coverage(ar, None, [])
    conf = compute_confidence(cr, ar, None)
    # first factor is the coverage base (effect = base - 1.0, <= 0);
    # every subsequent factor is a penalty or ceiling -> effect <= 0.
    for f in conf.factors:
        assert f.effect <= 1e-9


def test_monotonic_more_semantic_errors_never_raises_confidence(tmp_path) -> None:
    from app.analysis.service import AnalysisService
    from app.modernization.business_rules import BusinessRuleExtractor
    from app.modernization.flow.generator import generate_flow

    def score(src: str, name: str) -> float:
        p = tmp_path / name
        p.write_text(src, encoding="utf-8")
        r = AnalysisService().analyze_file(p)
        flow = generate_flow(r) if r.ir is not None else None
        rules = BusinessRuleExtractor().extract(r)
        cr = compute_coverage(r, flow, rules)
        return compute_confidence(cr, r, flow).score

    clean = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. C.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           DISPLAY WS-A.\n           STOP RUN.\n"
    )
    # same program but references an undefined variable -> semantic errors
    dirty = clean.replace(
        "DISPLAY WS-A.", "DISPLAY WS-UNDEFINED-1.\n           DISPLAY WS-UNDEFINED-2."
    )

    assert score(dirty, "d.cbl") <= score(clean, "c.cbl")
