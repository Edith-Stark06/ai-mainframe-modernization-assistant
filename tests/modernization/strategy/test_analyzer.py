"""Tests for ModernizationStrategyAnalyzer (task #114)."""

from __future__ import annotations

import textwrap

from app.modernization.business_rules import BusinessRuleExtractor
from app.modernization.flow.generator import generate_flow
from app.modernization.risk import RiskAnalyzer
from app.modernization.strategy import (
    ModernizationStrategy,
    ModernizationStrategyAnalyzer,
)


def _strategies(analyze, src: str):
    ar = analyze(textwrap.dedent(src))
    flow = generate_flow(ar)
    rules = BusinessRuleExtractor().extract(ar)
    risks = RiskAnalyzer().analyze(ar, flow, rules)
    recs = ModernizationStrategyAnalyzer().analyze(ar, flow, rules, risks)
    return ar, rules, risks, recs


def _kinds(recs):
    return {r.strategy for r in recs}


def _primary(recs):
    primaries = [r for r in recs if r.is_primary]
    assert len(primaries) == 1
    return primaries[0]


# ---------------------------------------------------------------------------


def test_trivial_program_recommends_rehost(analyze) -> None:
    _, _, _, recs = _strategies(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       PROCEDURE DIVISION.
       MAIN.
           DISPLAY 'HI'.
           STOP RUN.
    """,
    )
    assert _primary(recs).strategy is ModernizationStrategy.REHOST
    assert _primary(recs).confidence == 0.8


def test_clean_program_with_rules_recommends_refactor(analyze) -> None:
    _, _, _, recs = _strategies(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X VALUE SPACE.
       01 WS-B PIC X(4) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           IF WS-A = 'Y'
               MOVE 'OK' TO WS-B
           END-IF.
           STOP RUN.
    """,
    )
    prim = _primary(recs)
    assert prim.strategy is ModernizationStrategy.REFACTOR
    assert prim.evidence
    assert prim.rationale


def test_unsupported_heavy_program_recommends_rewrite_and_suppresses_rehost(
    analyze,
) -> None:
    lines = "\n".join(f"       01 WS-P{i} PIC 9(5) COMP-3 VALUE 0." for i in range(12))
    _, _, risks, recs = _strategies(
        analyze,
        f"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
{lines}
       01 WS-B PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           MOVE 'A' TO WS-B.
           STOP RUN.
    """,
    )
    prim = _primary(recs)
    assert prim.strategy is ModernizationStrategy.REWRITE
    assert prim.confidence == 1.0
    # REWRITE contradicts REHOST/REFACTOR — they must be suppressed.
    assert ModernizationStrategy.REHOST not in _kinds(recs)
    assert ModernizationStrategy.REFACTOR not in _kinds(recs)
    # It must reference the risks that triggered it.
    assert prim.referenced_risk_ids
    assert prim.prerequisites


def test_external_call_program_recommends_replatform(analyze) -> None:
    _, _, risks, recs = _strategies(
        analyze,
        """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN.
           CALL 'EXTSVC'.
           MOVE 'A' TO WS-A.
           STOP RUN.
    """,
    )
    assert ModernizationStrategy.REPLATFORM in _kinds(recs)
    replat = next(r for r in recs if r.strategy is ModernizationStrategy.REPLATFORM)
    assert any("EXTSVC" in e for e in replat.evidence)
    # references the EXTERNAL_CALL risk
    assert replat.referenced_risk_ids


def test_deterministic_and_single_primary(analyze, complex_analysis) -> None:
    flow = generate_flow(complex_analysis)
    rules = BusinessRuleExtractor().extract(complex_analysis)
    risks = RiskAnalyzer().analyze(complex_analysis, flow, rules)
    a = ModernizationStrategyAnalyzer().analyze(complex_analysis, flow, rules, risks)
    b = ModernizationStrategyAnalyzer().analyze(complex_analysis, flow, rules, risks)
    assert [r.to_dict() for r in a] == [r.to_dict() for r in b]
    assert sum(1 for r in a if r.is_primary) == 1
    ids = [r.recommendation_id for r in a]
    assert ids == [f"STRAT-{i:03d}" for i in range(1, len(a) + 1)]
    # primary listed first
    assert a[0].is_primary


def test_complex_fixture_primary_is_rewrite(complex_analysis) -> None:
    flow = generate_flow(complex_analysis)
    rules = BusinessRuleExtractor().extract(complex_analysis)
    risks = RiskAnalyzer().analyze(complex_analysis, flow, rules)
    recs = ModernizationStrategyAnalyzer().analyze(complex_analysis, flow, rules, risks)
    prim = _primary(recs)
    # The complex fixture has 30+ unsupported-construct occurrences.
    assert prim.strategy is ModernizationStrategy.REWRITE
    # Every referenced risk id actually exists in the risk list.
    all_ids = {r.risk_id for r in risks}
    for rec in recs:
        for rid in rec.referenced_risk_ids:
            assert rid in all_ids


def test_recommendations_have_distinct_rationale(complex_analysis) -> None:
    flow = generate_flow(complex_analysis)
    rules = BusinessRuleExtractor().extract(complex_analysis)
    risks = RiskAnalyzer().analyze(complex_analysis, flow, rules)
    recs = ModernizationStrategyAnalyzer().analyze(complex_analysis, flow, rules, risks)
    rationales = [r.rationale for r in recs]
    assert len(rationales) == len(set(rationales))
