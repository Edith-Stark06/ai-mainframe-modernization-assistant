"""Dependency analysis of a compound ``IF`` (``extra_conditions``).

``DependencyAnalyzer.visit_if_statement`` read only the first comparison, so
for ``IF WS-A > 5 OR WS-B = 2`` no ``CONDITION`` dependency was recorded for
``WS-B``. It now inspects every operand of every term, filtering literals
exactly as it does for the first term. The AST is the source of truth; nothing
is derived from rendered text.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.analysis.dependencies.analyzer import DependencyAnalyzer
from app.analysis.dependencies.models import DependencyType
from app.analysis.service import AnalysisService
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
    01 WS-CODE PIC X VALUE SPACE.
        88 IS-OK VALUE 'A'.
    PROCEDURE DIVISION.
    MAIN.
""")


def _deps(condition: str):
    source = _HEADER + f"    IF {condition}\n        MOVE 'Y' TO WS-R\n    END-IF.\n"
    program = ProgramParser().parse(CobolLexer().tokenize(source, filename="t.cbl"))
    return DependencyAnalyzer().analyze(program)


def _condition_targets(deps) -> list[str]:
    return [d.target for d in deps if d.type is DependencyType.CONDITION]


# --- 1. simple IF unchanged ---------------------------------------------


def test_simple_if_dependencies_unchanged():
    assert _condition_targets(_deps("WS-A > 5")) == ["WS-A"]


# --- 2-5. every variable of a compound condition ------------------------------


def test_and_term_variable_is_a_dependency():
    assert _condition_targets(_deps("WS-A > 5 AND WS-B = 2")) == ["WS-A", "WS-B"]


def test_or_term_variable_is_a_dependency():
    assert _condition_targets(_deps("WS-A > 5 OR WS-B = 2")) == ["WS-A", "WS-B"]


def test_multiple_terms_are_recorded_in_source_order():
    assert _condition_targets(_deps("WS-C = 1 AND WS-A > 5 OR WS-B = 2")) == [
        "WS-C",
        "WS-A",
        "WS-B",
    ]


def test_variable_on_the_right_hand_side_of_an_extra_term_is_a_dependency():
    assert _condition_targets(_deps("WS-A > 5 OR WS-B = WS-C")) == [
        "WS-A",
        "WS-B",
        "WS-C",
    ]


def test_condition_name_terms_are_dependencies():
    targets = _condition_targets(_deps("IS-OK AND WS-A > 5"))
    assert "IS-OK" in targets and "WS-A" in targets


# --- 6. literals never become dependencies ------------------------------------


@pytest.mark.parametrize(
    "condition",
    [
        "WS-A > 5 OR WS-B = 2",
        "WS-A > 5 AND WS-B = 'X'",
        "WS-A > 5.50 OR WS-B < 0.25",
        "WS-A > 5 OR WS-B = ' '",
    ],
)
def test_literals_never_become_dependencies(condition):
    targets = _condition_targets(_deps(condition))
    assert set(targets) == {"WS-A", "WS-B"}
    for literal in ("5", "2", "'X'", "X", "5.50", "0.25", "' '"):
        assert literal not in targets


# --- real corpus, real pipeline -----------------------------------------------


@pytest.fixture(scope="module")
def real_deps():
    cache: dict[str, list] = {}

    def load(filename: str):
        if filename not in cache:
            cache[filename] = (
                AnalysisService().analyze_file(SOURCES / filename).dependencies
            )
        return cache[filename]

    return load


def _condition_targets_of(deps) -> set[str]:
    return {d.target for d in deps if d.type is DependencyType.CONDITION}


# (file, IF line, first-term variable, extra-term variable that used to be lost)
REAL_EXTRA_TERMS = [
    ("account_eligibility.cbl", 67, "EXISTING-ACCOUNTS", "ANNUAL-INCOME"),
    ("condition_names_88.cbl", 54, "PHYSICAL-BRANCH", "TX-WITHDRAWAL"),
    ("credit_approval.cbl", 37, "BANKRUPTCY-FLAG", "CREDIT-SCORE"),
    ("credit_approval.cbl", 40, "CREDIT-SCORE", "DTI-PERCENTAGE"),
    ("credit_approval.cbl", 43, "CREDIT-SCORE", "DTI-PERCENTAGE"),
    ("daily_trans_report.cbl", 56, "FD-TX-VAL", "FD-TX-SUSPICIOUS"),
    ("insurance_claim.cbl", 37, "POLICE-REPORT-FILED", "CLAIM-AMOUNT"),
    ("insurance_claim.cbl", 40, "DRIVER-AGE", "DRIVER-AGE"),
    ("mortgage_service.cbl", 50, "OUT-CREDIT-STATUS", "IN-LTV-RATIO"),
    ("payment_gateway.cbl", 46, "AUTH-OUT-RESP-CODE", "AUTH-OUT-RESP-CODE"),
    ("pricing_tier.cbl", 69, "PAYMENT-METHOD", "PAYMENT-METHOD"),
]


@pytest.mark.parametrize(("filename", "line", "first", "extra"), REAL_EXTRA_TERMS)
def test_real_compound_if_records_the_variables_of_every_term(
    real_deps, filename, line, first, extra
):
    """CONDITION targets are recorded once per variable (first occurrence), so
    this asserts the variable set, not the line."""
    targets = _condition_targets_of(real_deps(filename))
    assert first in targets, f"{filename}:{line} {first}"
    assert extra in targets, f"{filename}:{line} {extra}"


def test_real_suspicious_flag_dependency_is_recorded(real_deps):
    """``FD-TX-SUSPICIOUS`` appears in daily_trans_report.cbl only as the ``OR``
    term of line 56 -- before the fix it had no CONDITION dependency at all."""
    deps = real_deps("daily_trans_report.cbl")
    assert [
        d.source_location.line
        for d in deps
        if d.type is DependencyType.CONDITION and d.target == "FD-TX-SUSPICIOUS"
    ] == [56]


def test_real_credit_score_580_term_dependency_is_recorded(real_deps):
    """``CREDIT-SCORE < 580`` is the OR term of credit_approval.cbl:37 -- the
    first place CREDIT-SCORE is read, so its (deduplicated) CONDITION
    dependency is attributed to line 37; the literal ``580`` is not one."""
    deps = real_deps("credit_approval.cbl")
    assert [
        d.source_location.line
        for d in deps
        if d.type is DependencyType.CONDITION and d.target == "CREDIT-SCORE"
    ] == [37]
    assert "580" not in [d.target for d in deps]


def test_real_wire_term_variable_and_no_literal_dependency(real_deps):
    deps = real_deps("pricing_tier.cbl")
    assert "PAYMENT-METHOD" in _condition_targets_of(deps)
    assert not [d for d in deps if "WIRE" in d.target.upper()]


def test_real_dependencies_never_contain_literals(real_deps):
    for filename in {f for f, *_ in REAL_EXTRA_TERMS}:
        for d in real_deps(filename):
            if d.type is DependencyType.CONDITION:
                assert not d.target.startswith(("'", '"')), (filename, d.target)
                assert not d.target.replace(".", "").lstrip("+-").isdigit(), (
                    filename,
                    d.target,
                )
