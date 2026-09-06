"""Tests for RiskAnalyzer (task #113) — every risk assertion checks evidence."""

from __future__ import annotations

import textwrap

from app.modernization.business_rules import BusinessRuleExtractor
from app.modernization.flow.generator import generate_flow
from app.modernization.risk import RiskAnalyzer, RiskCategory, RiskSeverity

_HEADER = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 0.
       01 WS-B PIC X VALUE SPACE.
       01 WS-C PIC X(4) VALUE SPACE.
       PROCEDURE DIVISION.
"""


def _analyze_risks(analyze, body: str):
    src = _HEADER + textwrap.dedent(body)
    ar = analyze(src)
    flow = generate_flow(ar)
    rules = BusinessRuleExtractor().extract(ar)
    return ar, RiskAnalyzer().analyze(ar, flow, rules)


def _by_cat(risks, cat: RiskCategory):
    return [r for r in risks if r.category is cat]


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------


def test_no_risks_for_trivial_program(analyze) -> None:
    _, risks = _analyze_risks(
        analyze, "       MAIN.\n           MOVE 1 TO WS-A.\n           STOP RUN.\n"
    )
    # A clean 1-statement program: no branching, no deps, no diagnostics.
    assert _by_cat(risks, RiskCategory.EXTERNAL_CALL) == []
    assert _by_cat(risks, RiskCategory.SHARED_MUTABLE_STATE) == []
    assert _by_cat(risks, RiskCategory.UNSUPPORTED_SYNTAX) == []
    assert _by_cat(risks, RiskCategory.DEEPLY_NESTED_CONDITIONS) == []


def test_external_call_detected_with_evidence(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n           CALL 'PAYSVC'.\n"
        "       P2.\n           CALL 'PAYSVC'.\n           STOP RUN.\n",
    )
    calls = _by_cat(risks, RiskCategory.EXTERNAL_CALL)
    assert len(calls) == 1
    risk = calls[0]
    assert "PAYSVC" in risk.title
    assert risk.severity is RiskSeverity.HIGH  # >1 call site
    assert risk.occurrence_count == 2
    assert any("CALL site" in e for e in risk.evidence)
    assert set(risk.affected_components) == {"P1", "P2"}
    assert risk.recommended_mitigation


def test_single_external_call_is_medium(analyze) -> None:
    _, risks = _analyze_risks(
        analyze, "       P1.\n           CALL 'X'.\n           STOP RUN.\n"
    )
    calls = _by_cat(risks, RiskCategory.EXTERNAL_CALL)
    assert len(calls) == 1
    assert calls[0].severity is RiskSeverity.MEDIUM


def test_perform_is_not_reported_as_external_call(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n           PERFORM P2.\n           STOP RUN.\n"
        "       P2.\n           MOVE 1 TO WS-A.\n",
    )
    assert _by_cat(risks, RiskCategory.EXTERNAL_CALL) == []


def test_unresolved_perform_target_from_perform_varying(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n"
        "           PERFORM VARYING WS-A FROM 1 BY 1 UNTIL WS-A > 5\n"
        "               MOVE 1 TO WS-B\n"
        "           END-PERFORM.\n           STOP RUN.\n",
    )
    unresolved = _by_cat(risks, RiskCategory.UNRESOLVED_PERFORM_TARGET)
    assert len(unresolved) == 1
    assert any("VARYING" in e for e in unresolved[0].evidence)
    assert unresolved[0].severity is RiskSeverity.MEDIUM


def test_shared_mutable_state_two_paragraphs_is_medium(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n           MOVE 1 TO WS-A.\n"
        "       P2.\n           MOVE 2 TO WS-A.\n           STOP RUN.\n",
    )
    shared = _by_cat(risks, RiskCategory.SHARED_MUTABLE_STATE)
    assert len(shared) == 1
    assert shared[0].severity is RiskSeverity.MEDIUM
    assert "WS-A" in shared[0].title
    assert shared[0].confidence == 0.75
    assert set(shared[0].affected_components) == {"P1", "P2"}


def test_shared_mutable_state_three_paragraphs_is_high(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n           MOVE 1 TO WS-A.\n"
        "       P2.\n           MOVE 2 TO WS-A.\n"
        "       P3.\n           MOVE 3 TO WS-A.\n           STOP RUN.\n",
    )
    shared = _by_cat(risks, RiskCategory.SHARED_MUTABLE_STATE)
    assert len(shared) == 1
    assert shared[0].severity is RiskSeverity.HIGH


def test_variable_written_in_one_paragraph_is_not_shared(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n           MOVE 1 TO WS-A.\n           MOVE 2 TO WS-A.\n"
        "           STOP RUN.\n",
    )
    assert _by_cat(risks, RiskCategory.SHARED_MUTABLE_STATE) == []


def test_deeply_nested_conditions_depth_three_medium(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n"
        "           IF WS-B = 'A'\n"
        "               IF WS-A > 1\n"
        "                   IF WS-A < 9\n"
        "                       MOVE 'Y' TO WS-B\n"
        "                   END-IF\n"
        "               END-IF\n"
        "           END-IF.\n           STOP RUN.\n",
    )
    nested = _by_cat(risks, RiskCategory.DEEPLY_NESTED_CONDITIONS)
    assert len(nested) == 1
    assert nested[0].severity is RiskSeverity.MEDIUM
    assert "depth 3" in nested[0].title
    assert nested[0].confidence == 0.75


def test_shallow_nesting_not_reported(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n           IF WS-B = 'A'\n               MOVE 'Y' TO WS-C\n"
        "           END-IF.\n           STOP RUN.\n",
    )
    assert _by_cat(risks, RiskCategory.DEEPLY_NESTED_CONDITIONS) == []


def test_unsupported_syntax_from_comp3(analyze) -> None:
    src = textwrap.dedent("""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-PACKED PIC 9(7) COMP-3 VALUE 0.
       01 WS-B PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       P1.
           MOVE 'A' TO WS-B.
           STOP RUN.
    """)
    ar = analyze(src)
    flow = generate_flow(ar)
    risks = RiskAnalyzer().analyze(ar, flow, BusinessRuleExtractor().extract(ar))
    unsup = _by_cat(risks, RiskCategory.UNSUPPORTED_SYNTAX)
    data = _by_cat(risks, RiskCategory.DATA_COMPLEXITY)
    assert unsup and all(r.severity is RiskSeverity.HIGH for r in unsup)
    assert data and data[0].severity is RiskSeverity.MEDIUM
    assert any("COMP-3" in e for r in data for e in r.evidence)


def test_undocumented_business_rules_low_and_aggregate(analyze) -> None:
    _, risks = _analyze_risks(
        analyze,
        "       P1.\n           IF WS-B = 'A'\n               MOVE 'X' TO WS-C\n"
        "           END-IF.\n           STOP RUN.\n",
    )
    undoc = _by_cat(risks, RiskCategory.UNDOCUMENTED_BUSINESS_RULES)
    assert len(undoc) == 1
    assert undoc[0].severity is RiskSeverity.LOW
    assert undoc[0].occurrence_count >= 1


def test_no_business_rules_no_undocumented_risk(analyze) -> None:
    _, risks = _analyze_risks(
        analyze, "       P1.\n           MOVE 1 TO WS-A.\n           STOP RUN.\n"
    )
    assert _by_cat(risks, RiskCategory.UNDOCUMENTED_BUSINESS_RULES) == []


# ---------------------------------------------------------------------------
# Determinism, ids, ordering, dedup
# ---------------------------------------------------------------------------


def test_deterministic_ids_and_ordering(analyze) -> None:
    ar, risks1 = _analyze_risks(
        analyze,
        "       P1.\n           CALL 'X'.\n           MOVE 1 TO WS-A.\n"
        "       P2.\n           MOVE 2 TO WS-A.\n           STOP RUN.\n",
    )
    flow = generate_flow(ar)
    risks2 = RiskAnalyzer().analyze(ar, flow, BusinessRuleExtractor().extract(ar))
    assert [r.to_dict() for r in risks1] == [r.to_dict() for r in risks2]
    # ordered by severity (CRITICAL/HIGH first)
    from app.modernization.risk.models import SEVERITY_ORDER

    order = [SEVERITY_ORDER[r.severity] for r in risks1]
    assert order == sorted(order)
    # ids are unique and category-scoped
    ids = [r.risk_id for r in risks1]
    assert len(ids) == len(set(ids))
    assert all(r.risk_id.startswith("RISK-") for r in risks1)


def test_complex_fixture_risks(complex_analysis) -> None:
    flow = generate_flow(complex_analysis)
    rules = BusinessRuleExtractor().extract(complex_analysis)
    risks = RiskAnalyzer().analyze(complex_analysis, flow, rules)
    assert len(risks) > 0
    cats = {r.category for r in risks}
    # The complex fixture is known to contain COMP-3, unsupported verbs,
    # recoverable syntax errors, PERFORM VARYING, and cross-paragraph
    # writes.
    assert RiskCategory.UNSUPPORTED_SYNTAX in cats
    assert RiskCategory.SYNTAX_ERROR in cats
    assert RiskCategory.SHARED_MUTABLE_STATE in cats
    assert RiskCategory.DATA_COMPLEXITY in cats
    # Never fabricates an external CALL — the fixture has none.
    assert RiskCategory.EXTERNAL_CALL not in cats
    for r in risks:
        assert r.evidence
        assert r.recommended_mitigation
        assert 0.0 <= r.confidence <= 1.0


def test_complex_fixture_deterministic(complex_analysis) -> None:
    flow = generate_flow(complex_analysis)
    rules = BusinessRuleExtractor().extract(complex_analysis)
    a = RiskAnalyzer().analyze(complex_analysis, flow, rules)
    b = RiskAnalyzer().analyze(complex_analysis, flow, rules)
    assert [r.to_dict() for r in a] == [r.to_dict() for r in b]
