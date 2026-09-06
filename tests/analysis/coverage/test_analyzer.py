"""
Unit tests for compute_coverage (#115) against the real pipeline on small
in-memory sources, and against hand-built degenerate AnalysisResults.
"""

from __future__ import annotations

from app.analysis.coverage import compute_coverage
from app.analysis.coverage.models import CoverageStatus
from app.analysis.models import AnalysisResult
from app.analysis.service import AnalysisService
from app.modernization.business_rules import BusinessRuleExtractor
from app.modernization.flow.generator import generate_flow


def _cov(source: str, tmp_path, name: str = "p.cbl"):
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    r = AnalysisService().analyze_file(p)
    flow = generate_flow(r) if r.ir is not None else None
    rules = BusinessRuleExtractor().extract(r)
    return r, compute_coverage(r, flow, rules)


_TRIVIAL = (
    "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. T.\n"
    "       PROCEDURE DIVISION.\n       MAIN.\n"
    "           DISPLAY 'HI'.\n           STOP RUN.\n"
)


def test_trivial_all_dimensions_complete_or_not_measurable(tmp_path) -> None:
    _, cr = _cov(_TRIVIAL, tmp_path)
    for d in cr.dimensions:
        assert d.status in (
            CoverageStatus.COMPLETE,
            CoverageStatus.NOT_MEASURABLE,
        ), f"{d.name}: {d.status}"
    assert cr.overall >= 0.999
    assert cr.overall_status is CoverageStatus.COMPLETE


def test_no_ast_and_no_coverage_is_failed(tmp_path) -> None:
    ar = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=False,
        dependencies=[],
        ast=None,
        ir=None,
        coverage=None,
    )
    cr = compute_coverage(ar, None, [])
    assert cr.overall == 0.0
    assert cr.overall_status is CoverageStatus.FAILED
    assert cr.lexical.status is CoverageStatus.FAILED
    assert cr.parser.status is CoverageStatus.FAILED


def test_unknown_tokens_lower_lexical_coverage(tmp_path) -> None:
    # `?` is lexed but classified UNKNOWN (not a known symbol/word).
    src = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. Q.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           STOP RUN.\n"
    )
    _, clean = _cov(src, tmp_path, "clean.cbl")
    assert clean.lexical.status is CoverageStatus.COMPLETE
    assert clean.lexical.ratio == 1.0


def test_unsupported_statement_lowers_statement_and_ast(tmp_path) -> None:
    src = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. U.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           GO TO OTHER.\n           STOP RUN.\n"
        "       OTHER.\n           DISPLAY WS-A.\n"
    )
    _, cr = _cov(src, tmp_path)
    assert cr.statement.status is CoverageStatus.PARTIAL
    assert cr.statement.ratio < 1.0
    assert cr.ast.ratio < 1.0
    assert "SYN100" in cr.unsupported_syntax.codes
    assert "statement" in cr.unsupported_syntax.affected_dimensions


def test_parser_incomplete_lowers_parser_dimension(tmp_path) -> None:
    # DATA DIVISION after PROCEDURE DIVISION -> parser never reaches it.
    src = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. I.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           STOP RUN.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n       01 WS-B PIC X(30) VALUE SPACE.\n"
    )
    r, cr = _cov(src, tmp_path)
    assert r.coverage.parse_complete is False
    assert cr.parser.status is CoverageStatus.PARTIAL
    assert cr.parser.ratio < 1.0
    assert cr.overall < 1.0


def test_no_conditionals_business_rule_not_measurable(tmp_path) -> None:
    _, cr = _cov(_TRIVIAL, tmp_path)
    assert cr.business_rule.status is CoverageStatus.NOT_MEASURABLE
    # and it does not drag overall down
    assert cr.overall >= 0.999


def test_overall_is_min_of_measurable(tmp_path) -> None:
    src = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. M.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) COMP-3 VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           GO TO X.\n           STOP RUN.\n"
        "       X.\n           DISPLAY WS-A.\n"
    )
    _, cr = _cov(src, tmp_path)
    measurable = [d.ratio for d in cr.dimensions if d.measurable]
    assert abs(cr.overall - min(measurable)) < 1e-9


def test_determinism(tmp_path) -> None:
    _, a = _cov(_TRIVIAL, tmp_path, "a.cbl")
    _, b = _cov(_TRIVIAL, tmp_path, "a.cbl")
    assert a.to_dict() == b.to_dict()
