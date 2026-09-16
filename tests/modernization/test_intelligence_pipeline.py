"""
Integration, determinism, and complex-fixture regression tests for the
Phase 4 pipeline (#112 + #113 + #114 wired by
``analyze_modernization_intelligence``).
"""

from __future__ import annotations

import json

from app.modernization.flow.generator import generate_flow
from app.modernization.intelligence import (
    ModernizationIntelligenceResult,
    analyze_modernization_intelligence,
)
from app.modernization.strategy import ModernizationStrategy

# ---------------------------------------------------------------------------
# End-to-end wiring
# ---------------------------------------------------------------------------


def test_pipeline_runs_end_to_end(eligibility_analysis) -> None:
    result = analyze_modernization_intelligence(eligibility_analysis)
    assert isinstance(result, ModernizationIntelligenceResult)
    assert len(result.business_rules) >= 3
    assert len(result.strategies) >= 1
    assert result.primary_strategy is not None


def test_pipeline_reuses_supplied_flow(eligibility_analysis) -> None:
    flow = generate_flow(eligibility_analysis)
    r1 = analyze_modernization_intelligence(eligibility_analysis, flow=flow)
    r2 = analyze_modernization_intelligence(eligibility_analysis)
    assert r1.to_dict() == r2.to_dict()


def test_strategy_layer_consumes_rule_and_risk_layers(eligibility_analysis) -> None:
    result = analyze_modernization_intelligence(eligibility_analysis)
    # every referenced risk id resolves to a real risk
    risk_ids = {r.risk_id for r in result.risks}
    for rec in result.strategies:
        for rid in rec.referenced_risk_ids:
            assert rid in risk_ids
    # the undocumented-rules risk only appears because #112 produced rules
    if result.business_rules:
        assert any(
            rk.category.value == "UNDOCUMENTED_BUSINESS_RULES" for rk in result.risks
        )


def test_layers_are_independently_orderable(eligibility_analysis) -> None:
    result = analyze_modernization_intelligence(eligibility_analysis)
    assert [r.rule_id for r in result.business_rules] == sorted(
        r.rule_id for r in result.business_rules
    )
    # strategies: primary first
    assert result.strategies[0].is_primary


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_repeated_analysis_is_byte_identical(eligibility_analysis) -> None:
    runs = [
        json.dumps(
            analyze_modernization_intelligence(eligibility_analysis).to_dict(),
            sort_keys=True,
        )
        for _ in range(4)
    ]
    assert len(set(runs)) == 1


def test_complex_fixture_repeated_analysis_is_byte_identical(
    complex_analysis,
) -> None:
    runs = [
        json.dumps(
            analyze_modernization_intelligence(complex_analysis).to_dict(),
            sort_keys=True,
        )
        for _ in range(3)
    ]
    assert len(set(runs)) == 1


def test_fresh_analysis_objects_same_source_same_output(tmp_path) -> None:
    from tests.modernization.conftest import analyze_source

    text = """\
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
    """
    # Same source, same filename, two independent pipeline runs from
    # scratch — output must be byte-identical.
    a = analyze_source(text, tmp_path, "same.cbl")
    b = analyze_source(text, tmp_path, "same.cbl")
    da = analyze_modernization_intelligence(a).to_dict()
    db = analyze_modernization_intelligence(b).to_dict()
    assert json.dumps(da, sort_keys=True) == json.dumps(db, sort_keys=True)


# ---------------------------------------------------------------------------
# Complex-fixture regression (exact deterministic expectations)
# ---------------------------------------------------------------------------


def test_complex_fixture_intelligence_shape(complex_analysis) -> None:
    result = analyze_modernization_intelligence(complex_analysis)

    # #112 — business rules
    rules = result.business_rules
    assert len(rules) == 6
    assert [r.rule_id for r in rules] == [f"BR-{i:03d}" for i in range(1, 7)]
    assert all(r.source_locations for r in rules)
    assert all(0.0 <= r.confidence <= 1.0 for r in rules)

    # #113 — risks
    risks = result.risks
    cats = {r.category.value for r in risks}
    assert "UNSUPPORTED_SYNTAX" in cats
    assert "SYNTAX_ERROR" in cats
    assert "SHARED_MUTABLE_STATE" in cats
    assert "DATA_COMPLEXITY" in cats
    assert "UNRESOLVED_PERFORM_TARGET" in cats
    assert "EXTERNAL_CALL" not in cats  # the fixture has no CALLs
    assert all(r.evidence and r.recommended_mitigation for r in risks)
    # severity ordering
    from app.modernization.risk.models import SEVERITY_ORDER

    sev = [SEVERITY_ORDER[r.severity] for r in risks]
    assert sev == sorted(sev)

    # #114 — strategies
    strategies = result.strategies
    assert strategies[0].is_primary
    assert strategies[0].strategy is ModernizationStrategy.REWRITE
    assert sum(1 for s in strategies if s.is_primary) == 1
    assert [s.recommendation_id for s in strategies] == [
        f"STRAT-{i:03d}" for i in range(1, len(strategies) + 1)
    ]


def test_complex_fixture_to_dict_is_json_serializable(complex_analysis) -> None:
    result = analyze_modernization_intelligence(complex_analysis)
    json.dumps(result.to_dict())
