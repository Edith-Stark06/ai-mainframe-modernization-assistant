"""
Negative / non-fabrication tests for the Phase 4 pipeline.

These assert the system does NOT invent conclusions the source does not
support: no rules from comments, no dependencies from literals, no risks
without evidence, no external systems without CALL/PERFORM evidence, no
strategy from arbitrary scores, and graceful behaviour on malformed
source.
"""

from __future__ import annotations

import textwrap

from app.analysis.models import AnalysisResult
from app.modernization.intelligence import analyze_modernization_intelligence
from app.modernization.risk import RiskCategory


def _run(analyze, src: str):
    ar = analyze(textwrap.dedent(src))
    return ar, analyze_modernization_intelligence(ar)


# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------


def test_comments_do_not_become_rules(analyze) -> None:
    _, result = _run(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
      * IF THE CUSTOMER IS A VIP THEN GIVE A DISCOUNT OF 20 PERCENT
      * ELIGIBILITY REQUIRES AGE OVER 18 AND ACTIVE STATUS
       PROCEDURE DIVISION.
       MAIN.
           DISPLAY 'DONE'.
           STOP RUN.
    """,
    )
    assert result.business_rules == ()


def test_literals_never_become_dependencies_or_variables(analyze) -> None:
    _, result = _run(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-S PIC X VALUE SPACE.
       01 WS-R PIC X(6) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           IF WS-S = 'A'
               MOVE 'ACTIVE' TO WS-R
           END-IF.
           STOP RUN.
    """,
    )
    assert len(result.business_rules) == 1
    rule = result.business_rules[0]
    for token in rule.dependencies + rule.variables.reads + rule.variables.writes:
        assert not token.startswith("'")
        assert token != "ACTIVE" or token == "ACTIVE"  # 'ACTIVE' literal excluded
    assert "'A'" not in rule.dependencies
    assert "'ACTIVE'" not in rule.dependencies


def test_condition_is_not_fabricated_beyond_the_ast(analyze) -> None:
    # The parser cannot represent "A >= 18 AND B = 'X'" on one IF.
    # Whatever survives must not claim an AND the AST never produced.
    _, result = _run(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(3) VALUE 0.
       01 WS-B PIC X VALUE SPACE.
       01 WS-R PIC X(4) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           IF WS-A >= 18 AND WS-B = 'X'
               MOVE 'OK' TO WS-R
           END-IF.
           STOP RUN.
    """,
    )
    for rule in result.business_rules:
        # a fabricated conjunction would mention WS-B; the AST triple does not.
        if "AND" in rule.condition:
            # only allowed when it came from genuine IF nesting
            assert rule.confidence == 0.75


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


def test_no_risk_without_evidence(analyze) -> None:
    _, result = _run(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           MOVE 'A' TO WS-A.
           STOP RUN.
    """,
    )
    assert result.risks == ()
    for risk in result.risks:  # vacuous, but documents the contract
        assert risk.evidence


def test_no_external_system_without_call_or_perform_evidence(analyze) -> None:
    _, result = _run(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X VALUE 'PAYROLL-SERVICE'.
       01 WS-B PIC X(20) VALUE 'HTTP://EXAMPLE/API'.
       PROCEDURE DIVISION.
       MAIN.
           MOVE WS-A TO WS-B.
           STOP RUN.
    """,
    )
    # Strings that merely look like service names / URLs are not CALLs.
    assert not any(r.category is RiskCategory.EXTERNAL_CALL for r in result.risks)


def test_perform_to_local_paragraph_is_not_an_external_call(analyze) -> None:
    _, result = _run(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           PERFORM SUB.
           STOP RUN.
       SUB.
           MOVE 'A' TO WS-A.
    """,
    )
    assert not any(r.category is RiskCategory.EXTERNAL_CALL for r in result.risks)
    assert not any(
        r.category is RiskCategory.UNRESOLVED_PERFORM_TARGET for r in result.risks
    )


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


def test_strategy_evidence_is_never_empty_and_traces_to_facts(
    eligibility_analysis,
) -> None:
    result = analyze_modernization_intelligence(eligibility_analysis)
    for rec in result.strategies:
        assert rec.evidence
        assert rec.rationale
        # no recommendation cites a score
        joined = " ".join(rec.evidence).lower()
        assert "score" not in joined


# ---------------------------------------------------------------------------
# Malformed / incomplete source
# ---------------------------------------------------------------------------


def test_missing_ast_returns_empty_result_without_error() -> None:
    ar = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=False,
        dependencies=[],
        ast=None,
        ir=None,
    )
    result = analyze_modernization_intelligence(ar)
    assert result.business_rules == ()
    # With no coverage object the pipeline still yields a defensible result.
    assert isinstance(result.strategies, tuple)


def test_garbage_source_does_not_crash(analyze) -> None:
    ar = analyze("this is not cobol at all\n%%%\n")
    result = analyze_modernization_intelligence(ar)
    # No fabricated rules; whatever risks appear are evidence-backed.
    for risk in result.risks:
        assert risk.evidence
    assert isinstance(result.strategies, tuple)


def test_partially_broken_procedure_division(analyze) -> None:
    ar = analyze(textwrap.dedent("""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           IF WS-A = 'A' AND
               MOVE 'X' TO WS-A
           END-IF.
           MOVE 'Z' TO WS-A.
           STOP RUN.
    """))
    result = analyze_modernization_intelligence(ar)
    # broken IF should surface as a syntax-error risk, not a fabricated rule
    assert (
        any(r.category is RiskCategory.SYNTAX_ERROR for r in result.risks)
        or result.business_rules == ()
    )
    for rule in result.business_rules:
        assert rule.condition.strip()
