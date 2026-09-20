"""The legacy ``app.analysis.rules`` extractor and ``IfStatementNode.extra_conditions``.

This extractor is **active**: ``app/api/routers/analysis.py`` builds the
``/analysis`` API's ``business_rules`` from it (it is *not* on the MMIM dataset
path, which uses ``app.modernization.business_rules``). It read only the first
comparison of an IF, so ``IF A > 5 OR B = 2`` produced the rule condition
``A > 5`` and the else branch ``NOT (A > 5)``. It now keeps every term, in
source order: a pure-AND chain is further conjuncts of the enclosing ``AND``
stack, an OR-containing chain is parenthesised as one conjunct, and the ELSE
branch is ``NOT (<the whole condition>)``. AND binds tighter than OR (the
parser's documented precedence), so no re-grouping is invented.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.analysis.rules.extractor import BusinessRuleExtractor
from app.analysis.rules.normalization import normalize_business_rule
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

SOURCES = Path("data/sources/phase6-v2")

_HEADER = textwrap.dedent("""\
    IDENTIFICATION DIVISION.
    PROGRAM-ID. T.
    DATA DIVISION.
    WORKING-STORAGE SECTION.
    01 WS-A PIC 9(3) VALUE 0.
    01 WS-B PIC 9(3) VALUE 0.
    01 WS-C PIC 9(3) VALUE 0.
    01 WS-R PIC X(4) VALUE SPACE.
    PROCEDURE DIVISION.
    MAIN.
""")


def _extract(source: str):
    program = ProgramParser().parse(CobolLexer().tokenize(source, filename="t.cbl"))
    return BusinessRuleExtractor().extract(program)


def _conditions(body: str) -> list[str]:
    return [r.condition for r in _extract(_HEADER + body)]


_IF_ELSE = "    IF {c}\n        MOVE 'Y' TO WS-R\n    ELSE\n        MOVE 'N' TO WS-R\n    END-IF.\n"


# --- 1. simple IF unchanged ---------------------------------------------


def test_simple_if_and_else_unchanged():
    assert _conditions(_IF_ELSE.format(c="WS-A > 5")) == ["WS-A > 5", "NOT (WS-A > 5)"]


# --- 2-4. AND / OR / ordering ---------------------------------------------


def test_and_extra_condition_is_preserved():
    assert _conditions(_IF_ELSE.format(c="WS-A > 5 AND WS-B = 2")) == [
        "WS-A > 5 AND WS-B = 2",
        "NOT (WS-A > 5 AND WS-B = 2)",
    ]


def test_or_extra_condition_is_preserved():
    assert _conditions(_IF_ELSE.format(c="WS-A > 5 OR WS-B = 2")) == [
        "(WS-A > 5 OR WS-B = 2)",
        "NOT (WS-A > 5 OR WS-B = 2)",
    ]


def test_multiple_extra_conditions_keep_source_order_and_connectors():
    assert _conditions(_IF_ELSE.format(c="WS-C = 3 AND WS-A > 5 OR WS-B = 2")) == [
        "(WS-C = 3 AND WS-A > 5 OR WS-B = 2)",
        "NOT (WS-C = 3 AND WS-A > 5 OR WS-B = 2)",
    ]


def test_compound_nested_inside_an_enclosing_condition():
    inner_and = (
        "    IF WS-C = 1\n        IF WS-A > 5 AND WS-B = 2\n            MOVE 'Y' TO WS-R\n"
        "        END-IF\n    END-IF.\n"
    )
    assert _conditions(inner_and) == ["WS-C = 1 AND WS-A > 5 AND WS-B = 2"]
    inner_or = inner_and.replace("AND", "OR")
    assert _conditions(inner_or) == ["WS-C = 1 AND (WS-A > 5 OR WS-B = 2)"]


def test_normalization_of_a_compound_condition_keeps_every_term():
    rule = _extract(_HEADER + _IF_ELSE.format(c="WS-A > 5 OR WS-B = 2"))[0]
    assert normalize_business_rule(rule).condition == "( WS-A > 5 OR WS-B = 2 )"


# --- real corpus -----------------------------------------------------------


REAL = [
    ("account_eligibility.cbl", "ANNUAL-INCOME > 75000.00"),
    ("condition_names_88.cbl", "TX-WITHDRAWAL"),
    ("credit_approval.cbl", "CREDIT-SCORE < 580"),
    ("credit_approval.cbl", "DTI-PERCENTAGE <= 35.00"),
    ("daily_trans_report.cbl", "FD-TX-SUSPICIOUS = 'Y'"),
    ("insurance_claim.cbl", "CLAIM-AMOUNT > 5000.00"),
    ("insurance_claim.cbl", "DRIVER-AGE > 75"),
    ("mortgage_service.cbl", "IN-LTV-RATIO <= 80.00"),
    ("payment_gateway.cbl", "AUTH-OUT-RESP-CODE = '000'"),
    ("pricing_tier.cbl", "PAYMENT-METHOD = 'WIRE'"),
]


@pytest.mark.parametrize(("filename", "term"), REAL)
def test_real_extra_condition_term_appears_in_a_rule(filename, term):
    source = (SOURCES / filename).read_text(encoding="utf-8")
    conditions = [r.condition for r in _extract(source)]
    assert any(term in c for c in conditions), f"{filename}: {term!r} dropped"


def test_real_or_rules_are_parenthesised_conjuncts():
    source = (SOURCES / "pricing_tier.cbl").read_text(encoding="utf-8")
    conditions = [r.condition for r in _extract(source)]
    assert "(PAYMENT-METHOD = 'ACH' OR PAYMENT-METHOD = 'WIRE')" in conditions
    assert "NOT (PAYMENT-METHOD = 'ACH' OR PAYMENT-METHOD = 'WIRE')" in conditions
    assert "NOT (PAYMENT-METHOD = 'ACH')" not in conditions  # the old, wrong ELSE


def test_legacy_extractor_is_consumed_by_the_analysis_api():
    """Documents why this fix is required rather than optional."""
    router = Path("app/api/routers/analysis.py").read_text(encoding="utf-8")
    assert "from app.analysis.rules.extractor import BusinessRuleExtractor" in router
    assert "extractor = BusinessRuleExtractor()" in router
