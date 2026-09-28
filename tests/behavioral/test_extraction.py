"""#129 — deterministic behavioral test extraction."""

from __future__ import annotations

import json

from app.behavioral.extraction import (
    extract_behavioral_tests,
    generate_boundary_values,
    parse_condition,
)

# --- condition parsing -------------------------------------------------


def test_parses_simple_and_negated_numeric_conditions():
    c = parse_condition("WS-AGE >= 18")
    assert c is not None and c.variable == "WS-AGE" and not c.negated
    n = parse_condition("NOT (WS-AGE >= 18)")
    assert n is not None and n.negated and n.effective_operator == "<"


def test_boundary_values_bracket_the_threshold():
    c = parse_condition("WS-AMOUNT > 50000")
    vals = dict(generate_boundary_values(c))
    assert vals["49999"] is False
    assert vals["50000"] is False
    assert vals["50001"] is True


def test_unparseable_condition_returns_none():
    assert parse_condition("A AND B") is None


# --- true / false branch + boundary + business-rule coverage -----------


def test_true_and_false_branches_are_both_extracted(if_else_bundle):
    suite = extract_behavioral_tests(if_else_bundle)
    taken = {b.taken for t in suite.tests for b in t.expected_branches}
    assert taken == {True, False}


def test_boundary_condition_below_equal_above(combined_bundle):
    suite = extract_behavioral_tests(combined_bundle)
    inputs = {t.inputs[0].value for t in suite.tests}
    assert inputs == {"0", "1"}  # 0 (not > 0) / 1 (> 0) bracket the threshold 0


def test_arithmetic_calculation_is_captured(combined_bundle):
    suite = extract_behavioral_tests(combined_bundle)
    calc_tests = [t for t in suite.tests if t.expected_calculations]
    assert calc_tests
    calc = calc_tests[0].expected_calculations[0]
    assert calc.operator == "+"
    assert calc.target == "COUNTER"


def test_validation_error_condition_is_captured(elig_bundle):
    suite = extract_behavioral_tests(elig_bundle)
    error_tests = [t for t in suite.tests if t.expected_errors]
    assert error_tests
    err = error_tests[0].expected_errors[0]
    assert err.category in ("ERROR_CONDITION", "CONDITIONAL_VALIDATION")


def test_output_display_is_captured(if_else_bundle):
    suite = extract_behavioral_tests(if_else_bundle)
    outs = [o for t in suite.tests for o in t.expected_outputs if o.kind == "display"]
    assert {o.expected_value for o in outs} == {"ADULT", "MINOR"}


def test_state_transition_is_captured(status_bundle):
    suite = extract_behavioral_tests(status_bundle)
    state_tests = [t for t in suite.tests if t.expected_state_changes]
    assert state_tests
    sc = state_tests[0].expected_state_changes[0]
    assert sc.field and sc.to_value


def test_multiple_business_rules_are_grouped_per_paragraph(status_bundle):
    suite = extract_behavioral_tests(status_bundle)
    paragraphs = {b.paragraph for t in suite.tests for b in t.expected_branches}
    assert "ADVANCE-STATUS" in paragraphs and "REPORT-STATUS" in paragraphs


# --- executability: unsupported / unreachable / external dep -----------


def test_unperformed_paragraph_is_non_executable_with_reason(elig_bundle):
    """Renamed (task #stage36): ``eligibility_rules.cbl``'s three PERFORMed
    paragraphs (``CHECK-ELIGIBILITY``/``CALCULATE-TOTAL``/``REVIEW-AMOUNT``)
    used to all be ``BE009`` stubs -- COBOL PERFORM-to-paragraph had no real
    Java body at all -- so this fixture previously demonstrated the
    "stubbed paragraph" reason exclusively. Task #stage36 outlines every
    PERFORM-to-local-paragraph target into a real method, so all three now
    execute; only ``STATUS-STEP`` -- genuinely never PERFORMed by anyone in
    this source -- remains non-executable, for the *other*, still-real
    reason this suite always distinguished (``_represented_paragraphs`` in
    ``app/behavioral/extraction/extractor.py``, unchanged). Measured
    directly, not assumed."""
    suite = extract_behavioral_tests(elig_bundle)
    assert len(suite.executable_tests) == 8
    assert len(suite.non_executable_tests) == 2
    for t in suite.non_executable_tests:
        assert t.inconclusive_reason
        assert "never PERFORMed" in t.inconclusive_reason


def test_unreachable_paragraph_is_flagged_distinctly(elig_bundle):
    """task #stage36: only ``STATUS-STEP`` (never PERFORMed) remains
    non-executable in this fixture now -- see the previous test's
    docstring. The ``BE009``-stub reason is still a real, distinct code
    path in the extractor (unchanged; still exercised directly by
    ``tests/backend/test_java_generator.py``'s stub tests, which use a
    hand-built IR with an unresolvable target), just no longer
    demonstrated by *this* fixture, since none of its PERFORM targets are
    stubs any more."""
    suite = extract_behavioral_tests(elig_bundle)
    reasons = {t.inconclusive_reason for t in suite.non_executable_tests}
    assert reasons == {
        "paragraph STATUS-STEP has no representation in the generated Java "
        "(never PERFORMed from the entry paragraph)"
    }


def test_executable_case_has_no_inconclusive_reason(if_else_bundle):
    suite = extract_behavioral_tests(if_else_bundle)
    assert suite.executable_tests
    for t in suite.executable_tests:
        assert t.inconclusive_reason is None


def test_no_evidence_no_test_for_unrelated_call_dependency(call_bundle):
    # call.cbl has an external CALL but no business rule at all — #129
    # must not fabricate a behavioral expectation for it
    suite = extract_behavioral_tests(call_bundle)
    assert suite.tests == ()


# --- determinism / source & rule mapping -------------------------------


def test_extraction_is_deterministic(elig_bundle):
    a = extract_behavioral_tests(elig_bundle)
    b = extract_behavioral_tests(elig_bundle)
    assert [t.test_id for t in a.tests] == [t.test_id for t in b.tests]
    assert a.content_hash() == b.content_hash()
    assert json.dumps(a.to_dict()) == json.dumps(b.to_dict())


def test_test_ids_are_stable_content_hashes_not_random():
    from app.dataset.analysis_bundle import build_analysis_bundle
    import tempfile

    src = open("tests/golden/if_else.cbl").read()
    b1 = build_analysis_bundle("IFELSE", src, tempfile.mkdtemp())
    b2 = build_analysis_bundle("IFELSE", src, tempfile.mkdtemp())
    s1, s2 = extract_behavioral_tests(b1), extract_behavioral_tests(b2)
    assert [t.test_id for t in s1.tests] == [t.test_id for t in s2.tests]


def test_source_locations_point_at_real_lines(if_else_bundle):
    suite = extract_behavioral_tests(if_else_bundle)
    n_lines = len(if_else_bundle.source.splitlines())
    for t in suite.tests:
        for ref in t.source_refs:
            assert ref.source_id == "IFELSE"
            if ref.line_start is not None:
                assert 1 <= ref.line_start <= n_lines


def test_business_rule_ids_reference_real_rules(if_else_bundle):
    suite = extract_behavioral_tests(if_else_bundle)
    real = {r["rule_id"] for r in if_else_bundle.business_rules}
    for t in suite.tests:
        assert set(t.business_rule_ids) <= real
