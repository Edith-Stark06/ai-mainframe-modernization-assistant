"""STEP 13 — IS-TRUE / IS-FALSE condition-operator extraction fix.

``app.behavioral.extraction.conditions.parse_condition`` previously
rejected every business-rule condition string produced by the level-88
parser fix (``docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md``) — strings
of the shape ``<name> IS-TRUE <name>`` / ``<name> IS-FALSE <name>``,
optionally ``NOT (...)``-wrapped — for two independent reasons: the
outer ``_COND_RE`` regex's operator alternation did not include
``IS-TRUE``/``IS-FALSE``, and its literal alternation only accepted a
quoted string or a number, never a bare identifier (the condition-name
repeated on the right, per the parser's own representation choice — see
``ConditionTerm``/``IfStatementNode``). All 8 of ``t_condition_names_88``'s
real business rules use one of these operators (directly or inside an
``AND``-compound); before this fix every one of them failed to parse and
the source produced zero behavioral validation tests.

Root cause traced end to end (COBOL -> AST -> business rule ->
``ConditionTerm`` -> ``parse_condition`` -> behavioral extraction ->
VALIDATION_REASONING eligibility) before any code was changed:
``bundle.business_rules[i]["condition"]`` already carried the correct
``IS-TRUE``/``IS-FALSE`` text (produced by
``app/modernization/business_rules/extractor.py``, unmodified by this
fix); ``parse_condition`` was the sole point where it was rejected.

Of the 8 real rules, only the 2 that are a *single* condition-name term
(not part of an ``AND`` compound) become parseable by this fix --
compound conditions remain a pre-existing, documented, out-of-scope
limitation of ``parse_condition`` (it has never represented compound
``AND``/``OR`` conditions, regardless of operator), unrelated to
IS-TRUE/IS-FALSE and not addressed here.

A level-88 condition-name's *declared* ``VALUE``/``VALUES`` domain is not
present in the condition string at all (both operands are just the
condition-name, repeated) -- it lives only in the DATA DIVISION AST
(``ConditionNameNode.values``). ``generate_boundary_values`` and
``_evaluate`` therefore take an explicit ``known_values`` parameter that
the caller (``extract_behavioral_tests``, via the new
``_collect_condition_name_values`` helper) populates by reading the real
AST -- never fabricated, and empty (safely producing zero boundary
values, not an invented one) when no declaration can be found.
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

CONDITION_NAMES_88 = Path("data/sources/phase6-v2/condition_names_88.cbl")


def _bundle(sid: str, path: Path):
    return build_analysis_bundle(
        sid, path.read_text(encoding="utf-8"), tempfile.mkdtemp()
    )


# --- IS-TRUE / IS-FALSE parsing -----------------------------------------


def test_is_true_condition_name_parses():
    c = parse_condition("ONLINE-CHANNEL IS-TRUE ONLINE-CHANNEL")
    assert c is not None
    assert c.variable == "ONLINE-CHANNEL"
    assert c.operator == "IS-TRUE"
    assert c.is_condition_name is True
    assert c.is_numeric is False
    assert not c.negated


def test_is_false_condition_name_parses():
    c = parse_condition("TX-VALID-KIND IS-FALSE TX-VALID-KIND")
    assert c is not None
    assert c.variable == "TX-VALID-KIND"
    assert c.operator == "IS-FALSE"
    assert c.is_condition_name is True


def test_not_wrapped_is_true_folds_to_is_false():
    c = parse_condition("NOT (TX-DEPOSIT IS-TRUE TX-DEPOSIT)")
    assert c is not None
    assert c.negated is True
    assert c.operator == "IS-TRUE"
    assert c.effective_operator == "IS-FALSE"


def test_not_wrapped_is_false_folds_to_is_true():
    c = parse_condition("NOT (TX-VALID-KIND IS-FALSE TX-VALID-KIND)")
    assert c is not None
    assert c.effective_operator == "IS-TRUE"


def test_mismatched_operands_rejected_not_guessed():
    """The parser's own representation always repeats the same name on
    both sides; a string where they differ is not a shape this module's
    real caller ever legitimately produces, so it is rejected rather than
    guessed at (no invented semantics for an unexpected shape)."""
    assert parse_condition("TX-DEPOSIT IS-TRUE TX-WITHDRAWAL") is None


def test_lowercase_operator_still_parses_case_insensitively():
    c = parse_condition("tx-deposit is-true tx-deposit")
    assert c is not None
    assert c.operator == "IS-TRUE"
    assert c.variable == "TX-DEPOSIT"


# --- existing comparison operators: unaffected regression ---------------


def test_existing_integer_comparison_still_parses():
    c = parse_condition("WS-AMOUNT > 50000")
    assert c is not None
    assert c.operator == ">" and c.is_condition_name is False


def test_existing_decimal_comparison_still_parses():
    c = parse_condition("TAX-OUT-TAX-RATE = 0.00")
    assert c is not None
    assert c.is_numeric is True and c.is_condition_name is False


def test_bare_identifier_as_rhs_still_rejected_for_ordinary_operators():
    """Admitting a bare identifier as the right operand only ever applies
    to the IS-TRUE/IS-FALSE grammar (a separate regex) -- an ordinary
    relational operator with a bare-identifier right-hand side (a
    variable-vs-variable comparison) must remain unparseable, exactly as
    before this fix. This is the regression that would matter most: it
    proves _COND_RE's own literal alternation was never widened."""
    assert parse_condition("TX-DEPOSIT = TX-WITHDRAWAL") is None


def test_unparseable_compound_condition_still_rejected():
    assert parse_condition("A AND B") is None


def test_compound_and_condition_with_is_true_still_unparseable():
    """A pre-existing, documented, out-of-scope limitation: parse_condition
    has never represented compound AND/OR conditions, for any operator.
    This is not something this fix changes or should change."""
    assert (
        parse_condition(
            "(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND (TX-AMOUNT > 1000.00)"
        )
        is None
    )


# --- boundary-value generation: real declared domain, never fabricated --


def test_is_true_boundary_values_use_declared_domain():
    c = parse_condition("ONLINE-CHANNEL IS-TRUE ONLINE-CHANNEL")
    vals = dict(generate_boundary_values(c, known_values=("WEB", "MOB", "API")))
    assert vals == {"WEB": True, "MOB": True, "API": True, "OTHER": False}


def test_is_false_boundary_values_use_declared_domain():
    c = parse_condition("TX-VALID-KIND IS-FALSE TX-VALID-KIND")
    vals = dict(generate_boundary_values(c, known_values=("D", "W", "T", "F")))
    assert vals == {"D": False, "W": False, "T": False, "F": False, "OTHER": True}


def test_negated_is_true_boundary_values_flip_correctly():
    c = parse_condition("NOT (TX-DEPOSIT IS-TRUE TX-DEPOSIT)")
    vals = dict(generate_boundary_values(c, known_values=("D",)))
    assert vals == {"D": False, "OTHER": True}


def test_no_known_values_yields_no_boundary_values_not_fabricated():
    """When the caller cannot find the condition-name's declaration in the
    AST, no boundary value is invented -- an empty list, the same honest
    "no derivable test" outcome an unparseable condition already produces
    elsewhere in this module."""
    c = parse_condition("SOME-FLAG IS-TRUE SOME-FLAG")
    assert generate_boundary_values(c) == []
    assert generate_boundary_values(c, known_values=()) == []


def test_multi_value_condition_name_all_declared_values_become_true_points():
    """A condition-name with more than one declared VALUE (the plural
    VALUES form) contributes one true-boundary point per declared value,
    not just one arbitrary representative -- every one of them genuinely
    makes the condition hold."""
    c = parse_condition("TX-VALID-KIND IS-TRUE TX-VALID-KIND")
    vals = generate_boundary_values(c, known_values=("D", "W", "T", "F"))
    true_points = {v for v, taken in vals if taken}
    false_points = {v for v, taken in vals if not taken}
    assert true_points == {"D", "W", "T", "F"}
    assert false_points == {"OTHER"}


def test_boundary_value_dedup_and_other_collision_avoided():
    """If a declared value happens to literally be 'OTHER', the
    synthesized non-member sentinel steps to 'OTHER1' rather than
    colliding with (and silently shadowing) a real declared value."""
    c = parse_condition("X IS-TRUE X")
    vals = dict(generate_boundary_values(c, known_values=("OTHER", "OTHER", "Y")))
    assert vals == {"OTHER": True, "Y": True, "OTHER1": False}


# --- real corpus: t_condition_names_88 end-to-end ------------------------


@pytest.fixture(scope="module")
def condition_names_88_bundle():
    return _bundle("t_condition_names_88", CONDITION_NAMES_88)


def test_real_corpus_business_rule_conditions_now_parseable(condition_names_88_bundle):
    rules = condition_names_88_bundle.business_rules or []
    assert len(rules) == 8
    single_term_conditions = [
        str(r["condition"]) for r in rules if " AND " not in str(r["condition"])
    ]
    # exactly the 2 non-compound rules become parseable by this fix
    assert len(single_term_conditions) == 2
    for cond in single_term_conditions:
        cmp = parse_condition(cond)
        assert cmp is not None, f"still unparseable: {cond!r}"
        assert cmp.is_condition_name


def test_real_corpus_compound_conditions_remain_unparseable_not_a_regression(
    condition_names_88_bundle,
):
    """The 6 AND-compound rules stay unparseable -- a pre-existing,
    documented limitation this fix does not touch or claim to fix."""
    rules = condition_names_88_bundle.business_rules or []
    compound_conditions = [
        str(r["condition"]) for r in rules if " AND " in str(r["condition"])
    ]
    assert len(compound_conditions) == 6
    for cond in compound_conditions:
        assert parse_condition(cond) is None


def test_critical_regression_condition_names_88_produces_real_validation_tests(
    condition_names_88_bundle,
):
    """The most important regression: t_condition_names_88 now produces
    genuine behavioral tests with real conditions, real expected outputs,
    and valid source provenance. Before this fix, every one of its 8
    business-rule conditions was rejected by parse_condition and
    extract_behavioral_tests produced zero tests."""
    suite = extract_behavioral_tests(condition_names_88_bundle)
    assert len(suite.tests) > 0

    conditions_seen = {b.condition for t in suite.tests for b in t.expected_branches}
    assert "TX-VALID-KIND IS-FALSE TX-VALID-KIND" in conditions_seen
    assert "ONLINE-CHANNEL IS-TRUE ONLINE-CHANNEL" in conditions_seen

    for t in suite.tests:
        # every test traces to a real source location -- never fabricated
        if t.expected_outputs or t.expected_state_changes:
            assert t.source_refs, f"{t.test_id} has evidence but no provenance"
            for ref in t.source_refs:
                assert ref.source_id == "t_condition_names_88"
                assert ref.line_start > 0 and ref.line_end >= ref.line_start


def test_real_corpus_true_branch_has_valid_evidence(condition_names_88_bundle):
    """ONLINE-CHANNEL IS-TRUE fires for each of its 3 declared values
    (WEB, MOB, API) and produces the real action from the source
    (`IF ONLINE-CHANNEL MOVE 0.00 TO FEES-LEVIED END-IF`, lines 61-62)."""
    suite = extract_behavioral_tests(condition_names_88_bundle)
    true_branch_tests = [
        t
        for t in suite.tests
        if any(
            b.taken and b.condition == "ONLINE-CHANNEL IS-TRUE ONLINE-CHANNEL"
            for b in t.expected_branches
        )
    ]
    assert len(true_branch_tests) == 3
    input_values = {t.inputs[0].value for t in true_branch_tests}
    assert input_values == {"WEB", "MOB", "API"}
    for t in true_branch_tests:
        assert any(
            o.name == "FEES-LEVIED" and o.expected_value == "0.00"
            for o in t.expected_outputs
        )
        assert t.source_refs
        ref = t.source_refs[0]
        assert ref.line_start == 61 and ref.line_end == 62


def test_real_corpus_false_branch_has_valid_evidence(condition_names_88_bundle):
    """TX-VALID-KIND IS-FALSE fires only for the synthesized non-member
    value (OTHER) and produces the real action from the source
    (`IF NOT TX-VALID-KIND MOVE 'REJECT-BAD-KIND' ... MOVE 'R' ...`,
    lines 34-36)."""
    suite = extract_behavioral_tests(condition_names_88_bundle)
    false_flag_true_tests = [
        t
        for t in suite.tests
        if any(
            b.taken and b.condition == "TX-VALID-KIND IS-FALSE TX-VALID-KIND"
            for b in t.expected_branches
        )
    ]
    assert len(false_flag_true_tests) == 1
    t = false_flag_true_tests[0]
    assert t.inputs[0].value == "OTHER"
    output_names = {o.name for o in t.expected_outputs}
    assert output_names == {"OUTCOME-ACTION", "TX-STATUS-FLAG"}
    assert t.source_refs
    ref = t.source_refs[0]
    assert ref.line_start == 34 and ref.line_end == 36


def test_real_corpus_declared_domain_values_produce_no_fabricated_output(
    condition_names_88_bundle,
):
    """The 4 declared values of TX-VALID-KIND (D, W, T, F) each make
    IS-FALSE evaluate to False -- correctly producing zero outputs/state
    changes (nothing fires), not a fabricated assertion."""
    suite = extract_behavioral_tests(condition_names_88_bundle)
    by_input = {
        t.inputs[0].value: t
        for t in suite.tests
        if any(
            b.condition == "TX-VALID-KIND IS-FALSE TX-VALID-KIND"
            for b in t.expected_branches
        )
    }
    for member in ("D", "W", "T", "F"):
        t = by_input[member]
        assert not t.expected_outputs
        assert not t.expected_state_changes
        branch = next(
            b
            for b in t.expected_branches
            if b.condition == "TX-VALID-KIND IS-FALSE TX-VALID-KIND"
        )
        assert branch.taken is False


def test_real_corpus_validation_reasoning_eligibility_now_met(
    condition_names_88_bundle,
):
    """suite.tests is non-empty, which is exactly what
    MMIMDatasetBuilder(strict_eligibility=True) requires to stop skipping
    this source for VALIDATION_REASONING -- confirmed here at the
    extractor boundary, independent of the dataset-builder layer."""
    suite = extract_behavioral_tests(condition_names_88_bundle)
    assert len(suite.tests) > 0
