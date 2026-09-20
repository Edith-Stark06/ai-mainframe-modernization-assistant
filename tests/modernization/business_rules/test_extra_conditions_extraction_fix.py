"""``IfStatementNode.extra_conditions`` consumption in the business-rule engine.

The parser records a compound ``IF`` as the first
``condition_left/operator/right`` triple plus ``extra_conditions`` (each
term carries the ``AND``/``OR`` connector that joined it to the previous
one). ``BusinessRuleExtractor._walk`` used to read only the first triple,
so every rendered condition silently lost the remaining terms -- 11 IF
statements across 8 corpus sources, 5 of them ``OR`` (which *broadens* the
condition, so the old rule was not merely incomplete but wrong), and the
ELSE branch of such an IF was negated over the first term alone.

These tests pin the corrected contract (see
``docs/MMIM_EXTRA_CONDITIONS_FIX.md``):

* every term is kept, in source order, with its own connector;
* ``AND`` binds tighter than ``OR`` (the parser's documented precedence);
* a pure-AND chain is further conjuncts, an OR-containing chain is one
  explicit ``(a) OR (b)`` group, and the ELSE branch is the exact De Morgan
  complement (one ``NOT (...)`` conjunct per AND-run);
* an incomplete term makes the whole condition unrepresentable rather than
  emitting a partial one;
* ordinary single-term IFs are unchanged.

The real-corpus tests run the real sources through the real pipeline.
"""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from app.behavioral.extraction import extract_behavioral_tests
from app.behavioral.extraction.conditions import (
    parse_compound_condition,
    parse_condition,
)
from app.dataset.analysis_bundle import build_analysis_bundle
from app.modernization.business_rules import BusinessRuleExtractor
from app.modernization.business_rules.extractor import _condition_runs
from app.parser.ast.statements import ConditionTerm, IfStatementNode

SOURCES = Path("data/sources/phase6-v2")

_SRC = textwrap.dedent("""\
    IDENTIFICATION DIVISION.
    PROGRAM-ID. T.
    DATA DIVISION.
    WORKING-STORAGE SECTION.
    01 WS-A PIC 9(3) VALUE 0.
    01 WS-B PIC 9(3) VALUE 0.
    01 WS-C PIC 9(3) VALUE 0.
    01 WS-R PIC X(4) VALUE SPACE.
    01 WS-CODE PIC X VALUE SPACE.
        88 IS-OK VALUE 'A'.
    PROCEDURE DIVISION.
    MAIN.
""")


def _conditions(analyze, body: str) -> list[str]:
    source = _SRC + textwrap.indent(textwrap.dedent(body), "    ")
    return [r.condition for r in BusinessRuleExtractor().extract(analyze(source))]


def _bundle(sid: str, filename: str):
    text = (SOURCES / filename).read_text(encoding="utf-8")
    return build_analysis_bundle(sid, text, tempfile.mkdtemp())


# --- 1. existing behaviour is unchanged ---------------------------------


def test_plain_if_condition_and_else_unchanged(analyze):
    conds = _conditions(
        analyze, "IF WS-A > 5\n MOVE 'Y' TO WS-R\nELSE\n MOVE 'N' TO WS-R\nEND-IF.\n"
    )
    assert sorted(conds) == sorted(["WS-A > 5", "NOT (WS-A > 5)"])


def test_nested_plain_ifs_still_conjoin_unchanged(analyze):
    body = "IF WS-A > 5\n IF WS-B = 2\n  MOVE 'Y' TO WS-R\n END-IF\nEND-IF.\n"
    assert _conditions(analyze, body) == ["(WS-A > 5) AND (WS-B = 2)"]


# --- 2-4. AND / OR / ordering -------------------------------------------


def test_and_extra_condition_is_preserved(analyze):
    body = "IF WS-A > 5 AND WS-B = 2\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, body) == ["(WS-A > 5) AND (WS-B = 2)"]


def test_or_extra_condition_is_preserved(analyze):
    body = "IF WS-A > 5 OR WS-B = 2\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, body) == ["(WS-A > 5) OR (WS-B = 2)"]


def test_else_of_and_is_the_negated_conjunction(analyze):
    body = "IF WS-A > 5 AND WS-B = 2\n MOVE 'Y' TO WS-R\nELSE\n MOVE 'N' TO WS-R\nEND-IF.\n"
    assert sorted(_conditions(analyze, body)) == sorted(
        [
            "(WS-A > 5) AND (WS-B = 2)",
            "NOT ((WS-A > 5) AND (WS-B = 2))",
        ]
    )


def test_else_of_or_is_every_term_negated(analyze):
    body = (
        "IF WS-A > 5 OR WS-B = 2\n MOVE 'Y' TO WS-R\nELSE\n MOVE 'N' TO WS-R\nEND-IF.\n"
    )
    assert sorted(_conditions(analyze, body)) == sorted(
        [
            "(WS-A > 5) OR (WS-B = 2)",
            "(NOT (WS-A > 5)) AND (NOT (WS-B = 2))",
        ]
    )


def test_multiple_extra_conditions_keep_source_order(analyze):
    and3 = "IF WS-C = 3 AND WS-A > 5 AND WS-B = 2\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, and3) == ["(WS-C = 3) AND (WS-A > 5) AND (WS-B = 2)"]
    or3 = "IF WS-C = 3 OR WS-A > 5 OR WS-B = 2\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, or3) == ["(WS-C = 3) OR (WS-A > 5) OR (WS-B = 2)"]


def test_and_binds_tighter_than_or_and_is_made_explicit(analyze):
    body = "IF WS-A > 5 AND WS-B = 2 OR WS-C = 3\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, body) == ["((WS-A > 5) AND (WS-B = 2)) OR (WS-C = 3)"]
    body = "IF WS-A > 5 OR WS-B = 2 AND WS-C = 3\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, body) == ["(WS-A > 5) OR ((WS-B = 2) AND (WS-C = 3))"]


def test_else_of_mixed_chain_is_the_exact_de_morgan_complement(analyze):
    body = (
        "IF WS-A > 5 AND WS-B = 2 OR WS-C = 3\n MOVE 'Y' TO WS-R\n"
        "ELSE\n MOVE 'N' TO WS-R\nEND-IF.\n"
    )
    assert "(NOT ((WS-A > 5) AND (WS-B = 2))) AND (NOT (WS-C = 3))" in _conditions(
        analyze, body
    )


# --- nesting / level-88 terms -------------------------------------------


def test_and_compound_flattens_into_the_enclosing_conjunction(analyze):
    body = (
        "IF WS-C = 3\n IF WS-A > 5 AND WS-B = 2\n  MOVE 'Y' TO WS-R\n END-IF\nEND-IF.\n"
    )
    assert _conditions(analyze, body) == ["(WS-C = 3) AND (WS-A > 5) AND (WS-B = 2)"]


def test_or_compound_is_one_explicit_group_inside_an_enclosing_conjunction(analyze):
    body = (
        "IF WS-C = 3\n IF WS-A > 5 OR WS-B = 2\n  MOVE 'Y' TO WS-R\n END-IF\nEND-IF.\n"
    )
    assert _conditions(analyze, body) == ["(WS-C = 3) AND ((WS-A > 5) OR (WS-B = 2))"]


def test_condition_name_terms_inside_a_compound_keep_is_true_is_false(analyze):
    body = "IF IS-OK AND WS-A > 5\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, body) == ["(IS-OK IS-TRUE IS-OK) AND (WS-A > 5)"]
    body = "IF NOT IS-OK OR WS-A > 5\n MOVE 'Y' TO WS-R\nEND-IF.\n"
    assert _conditions(analyze, body) == ["(IS-OK IS-FALSE IS-OK) OR (WS-A > 5)"]


def test_compound_if_variables_include_every_term(analyze):
    source = (
        _SRC + "    IF WS-A > 5 OR WS-B = 2\n        MOVE 'Y' TO WS-R\n    END-IF.\n"
    )
    (rule,) = BusinessRuleExtractor().extract(analyze(source))
    assert set(rule.variables.conditions) == {"WS-A", "WS-B"}
    assert rule.confidence == 1.0  # a direct read of one IF, not an inference
    assert any("additional AND/OR term" in e for e in rule.evidence)


# --- fail safe ----------------------------------------------------------


def _if(extra: tuple[ConditionTerm, ...], first=("WS-A", ">", "5")):
    return IfStatementNode(
        start_position=None,  # type: ignore[arg-type]
        end_position=None,  # type: ignore[arg-type]
        condition_left=first[0],
        condition_operator=first[1],
        condition_right=first[2],
        then_statements=(),
        extra_conditions=extra,
    )


@pytest.mark.parametrize(
    "extra",
    [
        (ConditionTerm("AND", "", "=", "2"),),
        (ConditionTerm("AND", "WS-B", "", "2"),),
        (ConditionTerm("OR", "WS-B", "=", ""),),
        (ConditionTerm("XOR", "WS-B", "=", "2"),),
        (ConditionTerm("AND", "WS-B", "=", "2"), ConditionTerm("OR", "", "", "")),
    ],
)
def test_incomplete_term_makes_the_whole_condition_unrepresentable(extra):
    assert _condition_runs(_if(extra)) is None


def test_incomplete_first_term_is_unrepresentable():
    assert _condition_runs(_if((), first=("WS-A", "", "5"))) is None


def test_complete_terms_group_into_or_separated_and_runs():
    terms = (
        ConditionTerm("AND", "B", "=", "2"),
        ConditionTerm("OR", "C", "=", "3"),
        ConditionTerm("AND", "D", "=", "4"),
    )
    assert _condition_runs(_if(terms)) == [
        [("WS-A", ">", "5"), ("B", "=", "2")],
        [("C", "=", "3"), ("D", "=", "4")],
    ]


# --- downstream consumability -------------------------------------------


def test_rendered_compound_strings_are_consumable_by_behavioral_parsers(analyze):
    body = (
        "IF WS-A > 5 AND WS-B = 2\n MOVE 'Y' TO WS-R\nEND-IF\n"
        "IF WS-A > 9 OR WS-B = 4\n MOVE 'Z' TO WS-R\nELSE\n MOVE 'N' TO WS-R\nEND-IF.\n"
    )
    conds = _conditions(analyze, body)
    assert "(WS-A > 5) AND (WS-B = 2)" in conds
    assert "(WS-A > 9) OR (WS-B = 4)" in conds
    and_c = parse_compound_condition("(WS-A > 5) AND (WS-B = 2)")
    or_c = parse_compound_condition("(WS-A > 9) OR (WS-B = 4)")
    else_c = parse_compound_condition("(NOT (WS-A > 9)) AND (NOT (WS-B = 4))")
    assert "(NOT (WS-A > 9)) AND (NOT (WS-B = 4))" in conds
    assert and_c and and_c.connector == "AND" and len(and_c.terms) == 2
    assert or_c and or_c.connector == "OR" and len(or_c.terms) == 2
    # ELSE of an OR is the AND of the negated terms -- still consumable.
    assert else_c and else_c.connector == "AND"
    assert [t.effective_operator for t in else_c.terms] == ["<=", "<>"]


def test_negated_conjunction_is_not_consumable_and_fails_safely():
    """``NOT ((a) AND (b))`` is faithful but is a nested group the
    behavioral compound parser does not model -- it must yield no test
    rather than a mis-parsed one."""
    text = "NOT ((WS-A > 5) AND (WS-B = 2))"
    assert parse_condition(text) is None
    assert parse_compound_condition(text) is None


# --- real corpus, real pipeline -----------------------------------------

REAL_OR_CONDITIONS = [
    (
        "t_credit_approval",
        "credit_approval.cbl",
        "(BANKRUPTCY-FLAG = 'Y') OR (CREDIT-SCORE < 580)",
    ),
    (
        "t_daily_trans_report",
        "daily_trans_report.cbl",
        "(FD-TX-VAL > 10000.00) OR (FD-TX-SUSPICIOUS = 'Y')",
    ),
    (
        "t_insurance_claim",
        "insurance_claim.cbl",
        "(DRIVER-AGE < 21) OR (DRIVER-AGE > 75)",
    ),
    (
        "t_payment_gateway",
        "payment_gateway.cbl",
        "(AUTH-OUT-RESP-CODE = ' ') OR (AUTH-OUT-RESP-CODE = '000')",
    ),
    (
        "t_pricing_tier",
        "pricing_tier.cbl",
        "(PAYMENT-METHOD = 'ACH') OR (PAYMENT-METHOD = 'WIRE')",
    ),
]


@pytest.mark.parametrize(("sid", "filename", "expected"), REAL_OR_CONDITIONS)
def test_real_or_conditions_reach_the_business_rules(sid, filename, expected):
    rules = _bundle(sid, filename).business_rules or []
    assert expected in [r["condition"] for r in rules]


def test_real_and_extra_conditions_reach_the_business_rules():
    ins = _bundle("t_insurance_claim", "insurance_claim.cbl").business_rules or []
    assert "(POLICE-REPORT-FILED = 'N') AND (CLAIM-AMOUNT > 5000.00)" in [
        r["condition"] for r in ins
    ]
    acct = (
        _bundle("t_account_eligibility", "account_eligibility.cbl").business_rules or []
    )
    assert (
        "(ELIGIBILITY-FLAG = 'Y') AND (EXISTING-ACCOUNTS >= 3) AND (ANNUAL-INCOME > 75000.00)"
        in [r["condition"] for r in acct]
    )


def test_real_else_of_or_is_no_longer_negated_over_the_first_term_alone():
    conds = [
        r["condition"]
        for r in _bundle("t_pricing_tier", "pricing_tier.cbl").business_rules or []
    ]
    assert "(NOT (PAYMENT-METHOD = 'ACH')) AND (NOT (PAYMENT-METHOD = 'WIRE'))" in conds
    assert "NOT (PAYMENT-METHOD = 'ACH')" not in conds  # the old, wrong ELSE condition


@pytest.fixture(scope="module")
def cn88():
    return _bundle("t_condition_names_88", "condition_names_88.cbl")


def test_real_br006_br007_regain_the_tx_withdrawal_term(cn88):
    """``IF PHYSICAL-BRANCH AND TX-WITHDRAWAL`` (line 54) encloses both."""
    by_id = {r["rule_id"]: r["condition"] for r in cn88.business_rules}
    assert by_id["BR-006"] == (
        "(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND "
        "(TX-WITHDRAWAL IS-TRUE TX-WITHDRAWAL) AND (NOT (TX-AMOUNT > 1000.00))"
    )
    assert by_id["BR-007"] == (
        "(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND "
        "(TX-WITHDRAWAL IS-TRUE TX-WITHDRAWAL) AND (TX-AMOUNT > 1000.00)"
    )
    assert len(by_id) == 8  # rule count unchanged


def test_real_cn88_evidence_now_reproduces_the_cobol(cn88):
    """Line 54-58: the fee is only levied when the record is a *withdrawal*
    (``TX-TYPE-CODE = 'W'``) at a physical branch. Before this fix the
    ``taken=true`` tests never assigned ``TX-TYPE-CODE='W'``, so they did
    not reproduce the COBOL (default ``'D'``)."""
    fee_tests = [
        t
        for t in extract_behavioral_tests(cn88).tests
        for b in t.expected_branches
        if "TX-WITHDRAWAL IS-TRUE" in b.condition and "TX-AMOUNT" in b.condition
        if b.taken
    ]
    assert len(fee_tests) == 2  # BR-006 and BR-007
    for t in fee_tests:
        values = {i.name: i.value for i in t.inputs}
        assert values["TX-TYPE-CODE"] == "W"
        assert values["CHANNEL-ORIGIN"] in {"BRN", "ATM"}
    fees = {
        o.expected_value: {i.name: i.value for i in t.inputs}["TX-AMOUNT"]
        for t in fee_tests
        for o in t.expected_outputs
        if o.name == "FEES-LEVIED"
    }
    assert fees == {"5.00": "1000.01", "0.00": "999.99"}


def test_real_or_evidence_is_derived_from_declared_values_only():
    """OR tests for ``PAYMENT-METHOD = 'ACH' OR = 'WIRE'``: each true case
    uses one real branch value with the real 2.50 discount; the false case
    uses a value outside both -- nothing outside the source's own literals
    except the module's existing non-member sentinel."""
    tests = [
        (t, b)
        for t in extract_behavioral_tests(
            _bundle("t_pricing_tier", "pricing_tier.cbl")
        ).tests
        for b in t.expected_branches
        if b.condition == "(PAYMENT-METHOD = 'ACH') OR (PAYMENT-METHOD = 'WIRE')"
    ]
    assert len(tests) == 3
    for t, b in tests:
        value = {i.name: i.value for i in t.inputs}["PAYMENT-METHOD"]
        if b.taken:
            assert value in {"ACH", "WIRE"}
            assert {(o.name, o.expected_value) for o in t.expected_outputs} == {
                ("EARLY-PAY-DISCOUNT", "2.50")
            }
        else:
            assert value not in {"ACH", "WIRE"}
            assert not t.expected_outputs
    assert {
        v
        for t, b in tests
        if b.taken
        for v in [{i.name: i.value for i in t.inputs}["PAYMENT-METHOD"]]
    } == {
        "ACH",
        "WIRE",
    }


@pytest.mark.parametrize(
    ("sid", "filename"),
    [
        ("t_account_eligibility", "account_eligibility.cbl"),
        ("t_condition_names_88", "condition_names_88.cbl"),
        ("t_credit_approval", "credit_approval.cbl"),
        ("t_daily_trans_report", "daily_trans_report.cbl"),
        ("t_insurance_claim", "insurance_claim.cbl"),
        ("t_mortgage_service", "mortgage_service.cbl"),
        ("t_payment_gateway", "payment_gateway.cbl"),
        ("t_pricing_tier", "pricing_tier.cbl"),
    ],
)
def test_every_real_extra_condition_term_appears_in_some_rule(sid, filename):
    """AST-driven, no hand-written expectation: for every real IF with
    ``extra_conditions``, each extra term's own text must appear in at least
    one emitted rule condition of that source (either positively or under
    ``NOT``) -- i.e. nothing is silently dropped."""
    bundle = _bundle(sid, filename)
    ifs: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("extra_conditions") and "condition_left" in node:
                ifs.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(bundle.ast["procedure_division"])
    assert ifs, f"{sid}: expected at least one IF with extra_conditions"
    conditions = " || ".join(r["condition"] for r in bundle.business_rules or [])
    for node in ifs:
        for term in node["extra_conditions"]:
            text = f"{term['left']} {term['operator']} {term['right']}"
            assert text in conditions, f"{sid}: dropped term {text!r}"
