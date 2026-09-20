"""STEP 10 — decimal-literal condition extraction fix.

``app.behavioral.extraction.conditions.parse_condition`` previously
rejected any COBOL fixed-point decimal literal (``0.00``, ``12.50``,
``-1.25``, ...) in a comparison condition — not merely because
``_NUMERIC`` failed to recognise it as numeric, but because the *outer*
``_COND_RE`` regex's literal alternation (``-?\\d+``) could not match a
decimal at all, so the whole condition failed to parse and
``parse_condition`` returned ``None``. This silently dropped every
IF-guarded rule whose condition compares a fixed-point field to a decimal
literal — including, after the prior COMPUTE/EVALUATE-inside-IF-block
parser fix, both of ``t_billing_engine``'s newly fully-parsed IF
conditions.

These tests pin: integer behaviour is unchanged, decimal literals (zero,
positive, negative) now parse with every existing comparison operator,
malformed decimal syntax is still rejected (not silently swallowed), and
the real ``t_billing_engine`` source now produces genuine, evidence-backed
behavioral validation tests instead of none.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.behavioral.extraction import extract_behavioral_tests
from app.behavioral.extraction.conditions import (
    generate_boundary_values,
    parse_condition,
)
from app.dataset.analysis_bundle import build_analysis_bundle

BILLING_ENGINE = Path("data/sources/phase6-v2/billing_engine.cbl")


def _bundle(sid: str, path: Path):
    return build_analysis_bundle(
        sid, path.read_text(encoding="utf-8"), tempfile.mkdtemp()
    )


# --- integer literals: unchanged behaviour ------------------------------


def test_integer_literal_condition_still_parses():
    c = parse_condition("RATE = 0")
    assert c is not None
    assert c.literal == "0" and c.is_numeric is True


def test_integer_boundary_values_unchanged():
    c = parse_condition("WS-AMOUNT > 50000")
    vals = dict(generate_boundary_values(c))
    assert vals["49999"] is False
    assert vals["50000"] is False
    assert vals["50001"] is True
    # step is still 1 for a plain integer literal, and values remain
    # plain integer strings (no ".0" introduced)
    assert set(vals) == {"49999", "50000", "50001"}


def test_negative_integer_condition_still_parses_and_filters_as_before():
    c = parse_condition("RATE = -1")
    assert c is not None and c.literal == "-1" and c.is_numeric is True
    # pre-existing policy: candidates below zero are dropped; unchanged.
    assert generate_boundary_values(c) == [("0", False)]


# --- decimal literals: the fix ------------------------------------------


def test_zero_decimal_literal_condition_parses():
    c = parse_condition("TAX-OUT-TAX-RATE = 0.00")
    assert c is not None
    assert (
        c.literal == "0.00"
        and c.is_numeric is True
        and c.variable == "TAX-OUT-TAX-RATE"
    )


def test_zero_decimal_boundary_values_step_by_one_hundredth():
    c = parse_condition("RATE = 0.00")
    vals = dict(generate_boundary_values(c))
    assert vals["0.00"] is True
    assert vals["0.01"] is False
    # the negative candidate (-0.01) is dropped by the same non-negative
    # filter integers already use — no new value below zero appears
    assert "-0.01" not in vals


def test_positive_decimal_literal_condition_parses():
    c = parse_condition("RATE = 12.50")
    assert c is not None and c.literal == "12.50" and c.is_numeric is True
    vals = dict(generate_boundary_values(c))
    assert vals["12.49"] is False
    assert vals["12.50"] is True
    assert vals["12.51"] is False


def test_negative_decimal_literal_condition_parses():
    c = parse_condition("RATE = -1.25")
    assert c is not None
    assert c.literal == "-1.25" and c.is_numeric is True and not c.negated
    # mirrors the pre-existing negative-integer policy: every boundary
    # candidate (-1.26, -1.25, -1.24) is below zero, so none survive —
    # the same qualitative behaviour test_negative_integer_condition_...
    # pins for -1, just decimal-precise instead of integer-precise.
    assert generate_boundary_values(c) == []


@pytest.mark.parametrize(
    "op,expect",
    [
        (">=", {"12.49": False, "12.50": True, "12.51": True}),
        ("<=", {"12.49": True, "12.50": True, "12.51": False}),
        ("<>", {"12.49": True, "12.50": False, "12.51": True}),
        ("=", {"12.49": False, "12.50": True, "12.51": False}),
        (">", {"12.49": False, "12.50": False, "12.51": True}),
        ("<", {"12.49": True, "12.50": False, "12.51": False}),
    ],
)
def test_decimal_literal_with_every_supported_comparison_operator(op, expect):
    c = parse_condition(f"RATE {op} 12.50")
    assert c is not None and c.is_numeric is True
    vals = dict(generate_boundary_values(c))
    assert vals == expect


def test_decimal_literal_four_fractional_digits_steps_precisely():
    """PIC-driven precision (e.g. 9(2)V9999) must not be truncated to a
    coarser step — the step is derived from the literal's own precision,
    not a hardcoded two-decimal assumption."""
    c = parse_condition("FX-OUT-RATE = 0.0000")
    assert c is not None
    vals = dict(generate_boundary_values(c))
    assert vals["0.0000"] is True
    assert vals["0.0001"] is False


def test_not_wrapped_decimal_condition_parses():
    c = parse_condition("NOT (RATE = 0.00)")
    assert c is not None
    assert c.negated and c.effective_operator == "<>"
    vals = dict(generate_boundary_values(c))
    assert vals["0.00"] is False
    assert vals["0.01"] is True


# --- malformed decimal syntax: still rejected, not silently swallowed --


@pytest.mark.parametrize(
    "text",
    [
        "RATE = 0.",  # trailing dot, no fractional digits
        "RATE = .5",  # leading dot, no integer digits
        "RATE = 12.5X",  # trailing garbage
        "RATE = 12..5",  # double dot
        "RATE = 12,50",  # comma instead of dot (not a COBOL literal form)
        "RATE = 1.2.3",  # multiple dots
    ],
)
def test_malformed_decimal_syntax_still_rejected(text):
    assert parse_condition(text) is None


def test_unparseable_compound_condition_still_rejected():
    # unrelated pre-existing behaviour, pinned to prove this fix did not
    # broaden parse_condition into a general expression parser
    assert parse_condition("A AND B") is None


# --- real-corpus: t_billing_engine end-to-end ---------------------------


@pytest.fixture(scope="module")
def billing_engine_bundle():
    return _bundle("t_billing_engine", BILLING_ENGINE)


def test_billing_engine_conditions_are_now_parseable(billing_engine_bundle):
    rules = billing_engine_bundle.business_rules or []
    assert rules, "expected at least one business rule for t_billing_engine"
    conditions = [str(r.get("condition", "")) for r in rules]
    assert any("0.00" in c for c in conditions)
    for cond in conditions:
        assert parse_condition(cond) is not None, f"still unparseable: {cond!r}"


def test_critical_regression_billing_engine_produces_real_validation_tests(
    billing_engine_bundle,
):
    """The most important regression: t_billing_engine's decimal-guarded
    IF condition (TAX-OUT-TAX-RATE = 0.00) must now produce a genuine
    behavioral test — a real condition, a real expected output on the
    branch where it fires, and valid source provenance. Before this fix,
    parse_condition rejected the condition and extract_behavioral_tests
    produced zero tests for this source.
    """
    suite = extract_behavioral_tests(billing_engine_bundle)
    assert len(suite.tests) > 0, "t_billing_engine must have >=1 derivable test"

    true_branch_tests = [
        t
        for t in suite.tests
        if any(
            b.taken and b.paragraph == "1000-INVOKE-TAX-ENGINE"
            for b in t.expected_branches
        )
    ]
    assert true_branch_tests, "expected a test covering the condition-holds branch"

    t = true_branch_tests[0]
    # real condition, not a placeholder
    assert any(b.condition == "TAX-OUT-TAX-RATE = 0.00" for b in t.expected_branches)
    # real expected output — not an empty/fabricated assertion
    assert t.expected_outputs
    assert any(
        o.name == "TAX-OUT-TAX-RATE" and o.expected_value == "7.25"
        for o in t.expected_outputs
    )
    # valid source provenance — a real line range in the real source file
    assert t.source_refs
    ref = t.source_refs[0]
    assert ref.source_id == "t_billing_engine"
    assert ref.line_start > 0 and ref.line_end >= ref.line_start
    # the rule that fired is recorded, not silently dropped
    assert t.business_rule_ids


def test_billing_engine_false_branch_is_also_a_legitimate_branch_test(
    billing_engine_bundle,
):
    suite = extract_behavioral_tests(billing_engine_bundle)
    false_branch_tests = [
        t
        for t in suite.tests
        if any(
            (not b.taken) and b.paragraph == "1000-INVOKE-TAX-ENGINE"
            for b in t.expected_branches
        )
    ]
    assert false_branch_tests
    t = false_branch_tests[0]
    assert any(b.condition == "TAX-OUT-TAX-RATE = 0.00" for b in t.expected_branches)
    # nothing fires on the false branch -> no fabricated output/state
    assert not t.expected_outputs
    assert not t.expected_state_changes
