"""STEP 14 — compound AND/OR condition extraction fix.

``app.behavioral.extraction.conditions.parse_condition`` has never
represented a compound (``AND``/``OR``-joined) condition — by design, for
a single comparison term. 6 of ``t_condition_names_88``'s 8 real business
rules are compound, rendered by
``app.modernization.business_rules.extractor._render_condition`` as a
chain of parenthesized, optionally ``NOT``-wrapped terms joined by a
single, uniform connector, e.g.::

    (NOT (TX-VALID-KIND IS-FALSE TX-VALID-KIND)) AND (TX-DEPOSIT IS-TRUE TX-DEPOSIT)

AUDIT FINDING (before any code was changed): the compound structure is
**flattened into a string**, not genuinely lost upstream and not
partially represented elsewhere. Each parenthesized part, once its own
wrapping parens are stripped, is *already* exactly a string
``parse_condition`` can parse on its own (a plain comparison, a
condition-name term, either optionally ``NOT``-wrapped). Confirmed by
directly printing all 8 real business-rule condition strings and their
source AST before writing any fix, and by grepping the whole
business-rule extractor for any code path that could ever emit ``" OR "``
— none exists; every real compound condition in the current 45-source
corpus is exclusively ``AND``-joined, produced by nested-``IF``/``ELSE``
cascades accumulating enclosing context, never by a single ``IF``'s own
``AND``/``OR`` compound condition (which
``app.modernization.business_rules.extractor._walk`` never reads at all
-- ``IfStatementNode.extra_conditions`` is parsed by the prior parser
task but still unconsumed there: 11 IF statements across 8 corpus sources
carry them, including ``OR`` terms; a separate, independent, pre-existing
gap this task does not fix — see ``docs/MMIM_COMPOUND_CONDITION_FIX.md``
§6).

``parse_compound_condition`` therefore *composes* the existing
``parse_condition`` (recursing into each part) rather than reimplementing
comparison/condition-name grammar — no generic expression language, no
operator precedence, no arbitrary nesting: exactly the flat,
single-connector, single-level-of-parenthesization shape the real
pipeline can produce.

A corpus-wide before/after scan (not merely assumed) found the real
blast radius is **17 sources**, not just the one this task's brief names
as the primary regression target — most already had ≥1 boundary_partition
test and now gain more (their nested-IF-cascade rules were previously
silently dropped entirely); ``t_batch_acct_update`` goes from 0 to 4 and
becomes newly VALIDATION_REASONING-eligible.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.behavioral.extraction import extract_behavioral_tests
from app.behavioral.extraction.conditions import (
    evaluate_compound,
    generate_boundary_values,
    generate_compound_boundary_values,
    parse_compound_condition,
    parse_condition,
)
from app.behavioral.extraction.extractor import (
    _collect_condition_name_parents,
    _collect_condition_name_values,
)
from app.dataset.analysis_bundle import build_analysis_bundle

CONDITION_NAMES_88 = Path("data/sources/phase6-v2/condition_names_88.cbl")


def _bundle(sid: str, path: Path):
    return build_analysis_bundle(
        sid, path.read_text(encoding="utf-8"), tempfile.mkdtemp()
    )


# --- 1. existing single-term conditions: unaffected regression ----------


def test_existing_single_comparison_unaffected():
    c = parse_condition("WS-AMOUNT > 50000")
    assert c is not None and c.operator == ">"


def test_existing_condition_name_term_unaffected():
    c = parse_condition("TX-DEPOSIT IS-TRUE TX-DEPOSIT")
    assert c is not None and c.operator == "IS-TRUE"


def test_single_term_never_matches_compound_parser():
    """A plain, non-compound condition string is not this function's job
    -- it must return None, not misinterpret a bare comparison as a
    one-term "compound"."""
    assert parse_compound_condition("WS-AMOUNT > 50000") is None
    assert parse_compound_condition("TX-VALID-KIND IS-FALSE TX-VALID-KIND") is None


def test_existing_unparseable_condition_still_rejected():
    assert parse_condition("A AND B") is None  # bare, unparenthesized -- not this shape
    assert parse_compound_condition("A AND B") is None


# --- 2. two-term AND -----------------------------------------------------


def test_two_term_and_parses():
    cc = parse_compound_condition("(WS-AMOUNT > 100) AND (WS-STATUS = 'A')")
    assert cc is not None
    assert cc.connector == "AND"
    assert [t.variable for t in cc.terms] == ["WS-AMOUNT", "WS-STATUS"]


def test_two_term_and_evidence_must_satisfy_the_conjunction():
    """For AND: evidence must satisfy the relevant conjunction -- the
    "true" case's values make *every* term hold, not just one."""
    cc = parse_compound_condition("(WS-AMOUNT > 100) AND (WS-STATUS = 'A')")
    cases = generate_compound_boundary_values(cc, {})
    true_cases = [values for values, holds in cases if holds]
    assert len(true_cases) == 1
    values = true_cases[0]
    assert evaluate_compound(cc, values, {}) is True
    # both conjuncts individually hold for this assignment
    amount_term, status_term = cc.terms
    assert generate_boundary_values(amount_term)  # sanity: term itself parses/generates
    assert int(values["WS-AMOUNT"]) > 100
    assert values["WS-STATUS"] == "A"


def test_two_term_and_false_case_flips_exactly_one_conjunct():
    cc = parse_compound_condition("(WS-AMOUNT > 100) AND (WS-STATUS = 'A')")
    cases = generate_compound_boundary_values(cc, {})
    false_cases = [values for values, holds in cases if not holds]
    assert len(false_cases) == 1
    values = false_cases[0]
    assert evaluate_compound(cc, values, {}) is False
    assert int(values["WS-AMOUNT"]) <= 100  # the flipped conjunct
    assert values["WS-STATUS"] == "A"  # the other conjunct still holds


# --- 3. two-term OR (no real corpus source has one -- see module         --
#        docstring; a synthetic unit fixture is the only way to exercise --
#        this grammar path at all, honestly documented as such) ----------


def test_two_term_or_parses():
    cc = parse_compound_condition("(WS-AMOUNT > 100) OR (WS-STATUS = 'A')")
    assert cc is not None
    assert cc.connector == "OR"


def test_two_term_or_evidence_may_satisfy_an_appropriate_branch():
    """For OR: evidence may satisfy an appropriate branch -- one true case
    per term, each demonstrating that term alone is sufficient (the other
    term does not hold in that case)."""
    cc = parse_compound_condition("(WS-AMOUNT > 100) OR (WS-STATUS = 'A')")
    cases = generate_compound_boundary_values(cc, {})
    true_cases = [values for values, holds in cases if holds]
    assert len(true_cases) == 2
    for values in true_cases:
        assert evaluate_compound(cc, values, {}) is True


def test_two_term_or_false_case_requires_every_branch_to_fail():
    cc = parse_compound_condition("(WS-AMOUNT > 100) OR (WS-STATUS = 'A')")
    cases = generate_compound_boundary_values(cc, {})
    false_cases = [values for values, holds in cases if not holds]
    assert len(false_cases) == 1
    values = false_cases[0]
    assert evaluate_compound(cc, values, {}) is False
    assert int(values["WS-AMOUNT"]) <= 100
    assert values["WS-STATUS"] != "A"


def test_mixed_and_or_in_one_expression_rejected():
    """COBOL's own AND-binds-tighter-than-OR precedence for a genuinely
    mixed expression is deliberately not modeled -- rejected, not
    mis-evaluated with the wrong precedence."""
    assert parse_compound_condition("(A = 1) AND (B = 2) OR (C = 3)") is None


# --- 4. mixed condition-name and comparison terms in one compound -------


def test_mixed_condition_name_and_comparison_term():
    cc = parse_compound_condition(
        "(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND (TX-AMOUNT > 1000.00)"
    )
    assert cc is not None
    assert cc.terms[0].is_condition_name and not cc.terms[1].is_condition_name
    kv = {"PHYSICAL-BRANCH": ("BRN", "ATM")}
    cases = generate_compound_boundary_values(cc, kv)
    true_case = next(values for values, holds in cases if holds)
    assert true_case["PHYSICAL-BRANCH"] in ("BRN", "ATM")
    assert evaluate_compound(cc, true_case, kv) is True


# --- 5 & 6. IS-TRUE / IS-FALSE inside a compound -------------------------


def test_is_true_term_inside_compound():
    cc = parse_compound_condition("(TX-DEPOSIT IS-TRUE TX-DEPOSIT) AND (WS-AMOUNT > 0)")
    assert cc is not None
    assert cc.terms[0].operator == "IS-TRUE"


def test_is_false_term_inside_compound():
    cc = parse_compound_condition(
        "(TX-VALID-KIND IS-FALSE TX-VALID-KIND) AND (WS-AMOUNT > 0)"
    )
    assert cc is not None
    assert cc.terms[0].operator == "IS-FALSE"


def test_not_wrapped_condition_name_term_inside_compound_folds_correctly():
    """The real rule-2 shape: NOT(IS-FALSE) folds to IS-TRUE via the
    existing Comparison.effective_operator, unmodified by this fix."""
    cc = parse_compound_condition(
        "(NOT (TX-VALID-KIND IS-FALSE TX-VALID-KIND)) AND (TX-DEPOSIT IS-TRUE TX-DEPOSIT)"
    )
    assert cc is not None
    assert cc.terms[0].negated and cc.terms[0].effective_operator == "IS-TRUE"


# --- 7. multi-value level-88 condition name inside a compound -----------


def test_multi_value_condition_name_inside_compound_uses_declared_domain():
    """TX-VALID-KIND has 4 declared values (D, W, T, F) -- the compound's
    boundary generation must derive from that real domain, never invent
    one, exactly like the single-term case already does."""
    cc = parse_compound_condition(
        "(NOT (TX-VALID-KIND IS-FALSE TX-VALID-KIND)) AND (TX-DEPOSIT IS-TRUE TX-DEPOSIT)"
    )
    kv = {"TX-VALID-KIND": ("D", "W", "T", "F"), "TX-DEPOSIT": ("D",)}
    cases = generate_compound_boundary_values(cc, kv)
    true_case = next(values for values, holds in cases if holds)
    assert true_case["TX-VALID-KIND"] in ("D", "W", "T", "F")
    assert true_case["TX-DEPOSIT"] == "D"


def test_no_declared_domain_yields_no_cases_not_fabricated():
    """A condition-name term with no declared domain found (empty
    known_values) means no case involving it can be built -- nothing is
    invented in its place."""
    cc = parse_compound_condition(
        "(SOME-UNDECLARED-FLAG IS-TRUE SOME-UNDECLARED-FLAG) AND (WS-AMOUNT > 0)"
    )
    assert cc is not None
    assert generate_compound_boundary_values(cc, {}) == []


# --- 8. false/negative branches where the real corpus supports them -----


def test_decimal_boundary_stepping_used_inside_compound():
    """Decimal fixed-point terms inside a compound still step by their
    own literal's precision (Decimal-based, unchanged from the
    single-term path) -- not integer-rounded, not fabricated."""
    cc = parse_compound_condition(
        "(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND (TX-AMOUNT > 1000.00)"
    )
    kv = {"PHYSICAL-BRANCH": ("BRN",)}
    cases = generate_compound_boundary_values(cc, kv)
    amounts = {values["TX-AMOUNT"] for values, _ in cases}
    assert "1000.01" in amounts  # one unit past the literal's own 2-decimal precision


# --- 9. malformed/unsupported compound expressions fail safely ----------


@pytest.mark.parametrize(
    "text",
    [
        "(A = 1",  # unbalanced -- missing close paren
        "A = 1) AND (B = 2)",  # unbalanced -- missing open paren
        "(A = 1) AND (B AND C)",  # inner part is not itself parseable
        "(A = 1) XOR (B = 2)",  # unsupported connector
        "(A = 1) (B = 2)",  # missing connector entirely
        "(A = 1)",  # only one part -- not actually compound
    ],
)
def test_malformed_compound_fails_safely_not_fabricated(text):
    assert parse_compound_condition(text) is None


def test_malformed_compound_rule_excluded_not_crashed(tmp_path):
    """A source whose business rules happen to include something shaped
    like a compound but not actually parseable must not crash extraction
    -- the rule is silently excluded, exactly like an unparseable
    single-term condition already is."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T1.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       01 WS-B PIC 9(5) VALUE 2.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               MOVE 1 TO WS-B
           END-IF
           DISPLAY WS-B.
"""
    path = tmp_path / "probe.cbl"
    path.write_text(src, encoding="utf-8")
    bundle = build_analysis_bundle("PROBE", src, str(tmp_path))
    suite = extract_behavioral_tests(bundle)  # must not raise
    assert isinstance(suite.tests, tuple)


# --- real corpus: t_condition_names_88 end-to-end ------------------------


@pytest.fixture(scope="module")
def condition_names_88_bundle():
    return _bundle("t_condition_names_88", CONDITION_NAMES_88)


def test_real_corpus_all_six_compound_rules_now_parseable(condition_names_88_bundle):
    rules = condition_names_88_bundle.business_rules or []
    assert len(rules) == 8
    compound_conditions = [
        str(r["condition"]) for r in rules if " AND " in str(r["condition"])
    ]
    assert len(compound_conditions) == 6
    for cond in compound_conditions:
        cc = parse_compound_condition(cond)
        assert cc is not None, f"still unparseable: {cond!r}"
        assert cc.connector == "AND"


def test_critical_regression_condition_names_88_gains_compound_evidence(
    condition_names_88_bundle,
):
    """Before this fix: 9 tests (the 2 single-term rules only). After:
    21 -- the 6 compound rules each contribute real, evidence-backed
    tests derived from their own real declared domains and real actions,
    never fabricated."""
    suite = extract_behavioral_tests(condition_names_88_bundle)
    assert len(suite.tests) == 21

    compound_conditions_seen = {
        b.condition
        for t in suite.tests
        for b in t.expected_branches
        if " AND " in b.condition
    }
    assert len(compound_conditions_seen) == 6


def test_real_corpus_compound_evidence_has_valid_provenance_and_no_fabrication(
    condition_names_88_bundle,
):
    suite = extract_behavioral_tests(condition_names_88_bundle)
    compound_tests = [
        t
        for t in suite.tests
        if any(" AND " in b.condition for b in t.expected_branches)
    ]
    assert compound_tests
    for t in compound_tests:
        assert len(t.inputs) >= 1
        if t.expected_outputs or t.expected_state_changes:
            assert t.source_refs, f"{t.test_id} has evidence but no provenance"
            for ref in t.source_refs:
                assert ref.source_id == "t_condition_names_88"
                assert ref.line_start > 0
        else:
            # the negative-evidence case: branch not taken, nothing fired
            assert any(not b.taken for b in t.expected_branches)


def test_real_corpus_credit_account_rule_produces_correct_evidence(
    condition_names_88_bundle,
):
    """Rule BR-002: TX-VALID-KIND valid AND TX-DEPOSIT -> CREDIT-ACCOUNT.
    Spot-verified against the real source (lines 38-39)."""
    target_condition = "(NOT (TX-VALID-KIND IS-FALSE TX-VALID-KIND)) AND (TX-DEPOSIT IS-TRUE TX-DEPOSIT)"
    suite = extract_behavioral_tests(condition_names_88_bundle)
    fired = [
        t
        for t in suite.tests
        if any(b.taken and b.condition == target_condition for b in t.expected_branches)
    ]
    assert len(fired) == 1
    t = fired[0]
    assert any(
        o.name == "OUTCOME-ACTION" and o.expected_value == "CREDIT-ACCOUNT"
        for o in t.expected_outputs
    )
    assert t.source_refs
    ref = t.source_refs[0]
    assert ref.line_start == 38 and ref.line_end == 39


def test_real_corpus_deterministic_across_runs(condition_names_88_bundle):
    suite1 = extract_behavioral_tests(condition_names_88_bundle)
    suite2 = extract_behavioral_tests(condition_names_88_bundle)
    assert tuple(t.test_id for t in suite1.tests) == tuple(
        t.test_id for t in suite2.tests
    )


def test_real_corpus_compound_inputs_are_realizable_storage_locations(
    condition_names_88_bundle,
):
    """Every level-88 in this source is a condition on ONE shared parent
    (``TX-TYPE-CODE``) or on ``CHANNEL-ORIGIN``. Evidence must assign those
    real data items -- never a condition-name as if it were its own
    variable (``TX-VALID-KIND='D'`` together with ``TX-WITHDRAWAL='W'`` is
    impossible in real COBOL)."""
    parents = _collect_condition_name_parents(condition_names_88_bundle.ast)
    assert parents["TX-VALID-KIND"] == parents["TX-WITHDRAWAL"] == "TX-TYPE-CODE"
    assert parents["PHYSICAL-BRANCH"] == "CHANNEL-ORIGIN"

    suite = extract_behavioral_tests(condition_names_88_bundle)
    for t in suite.tests:
        if not any(" AND " in b.condition for b in t.expected_branches):
            continue
        names = [i.name for i in t.inputs]
        assert len(names) == len(set(names))
        assert not set(names) & set(parents), f"{t.test_id}: condition-name as input"


def test_real_corpus_every_compound_case_reverifies_against_its_own_condition(
    condition_names_88_bundle,
):
    """Independent re-evaluation: for every compound test, the recorded
    ``taken`` flag equals what ``evaluate_compound`` computes from the
    test's own inputs and the real declared domains."""
    kvs = _collect_condition_name_values(condition_names_88_bundle.ast)
    parents = _collect_condition_name_parents(condition_names_88_bundle.ast)
    checked = 0
    for t in extract_behavioral_tests(condition_names_88_bundle).tests:
        for b in t.expected_branches:
            compound = parse_compound_condition(b.condition)
            if compound is None:
                continue
            values = {i.name: i.value for i in t.inputs}
            assert evaluate_compound(compound, values, kvs, parents) is b.taken
            checked += 1
    assert checked == 12


# --- shared-parent aliasing, same-variable terms, underivable domains ----


def test_shared_parent_contradictory_conjunction_is_dropped_not_fabricated():
    c = parse_compound_condition("(A IS-TRUE A) AND (B IS-TRUE B)")
    assert c is not None
    kvs = {"A": ("X",), "B": ("Y",)}
    # independent variables: satisfiable
    assert generate_compound_boundary_values(c, kvs)
    # both are conditions on ONE storage location with disjoint domains:
    # A and B can never both hold, so no all-true (or any AND) case exists.
    assert generate_compound_boundary_values(c, kvs, {"A": "P", "B": "P"}) == []


def test_shared_parent_assigns_the_parent_once():
    c = parse_compound_condition("(A IS-TRUE A) AND (NOT (B IS-TRUE B))")
    assert c is not None
    kvs = {"A": ("X",), "B": ("Y",)}
    cases = generate_compound_boundary_values(c, kvs, {"A": "P", "B": "P"})
    assert cases
    for values, holds in cases:
        assert set(values) == {"P"}
        assert evaluate_compound(c, values, kvs, {"A": "P", "B": "P"}) is holds
    assert ({"P": "X"}, True) in cases


def test_same_variable_in_two_terms_is_verified_not_overwritten():
    c = parse_compound_condition("(X > 100) AND (X < 200)")
    assert c is not None
    cases = generate_compound_boundary_values(c)
    assert cases
    for values, holds in cases:
        assert set(values) == {"X"}
        assert evaluate_compound(c, values) is holds
    assert any(holds for _, holds in cases)


def test_contradictory_same_variable_conjunction_yields_no_true_case():
    c = parse_compound_condition("(X > 200) AND (X < 100)")
    assert c is not None
    assert generate_compound_boundary_values(c) == []


def test_condition_name_without_declared_domain_makes_compound_underivable():
    c = parse_compound_condition("(A IS-TRUE A) AND (X > 5)")
    assert c is not None
    assert generate_compound_boundary_values(c, {}) == []
