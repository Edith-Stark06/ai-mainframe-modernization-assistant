"""Java emission of a compound ``IF`` (``IRIf.extra_terms``).

``IF WS-A > 5 OR WS-B < 2`` used to generate ``if (wsA > 5) {`` -- the whole
``OR`` term vanished from the Java, changing the program's meaning. Every term
is now emitted, in source order, joined by ``&&``/``||``.

COBOL's ``=`` (emitted as Java ``==``) and the skipped-header fail-safe are
covered by ``test_java_if_emission_fix.py``; this file covers the compound
(``extra_terms``) emission itself.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.control_flow_emitter import emit_if
from app.ir.instructions import IRConditionTerm, IRIf

SOURCES = Path("data/sources/phase6-v2")


def _if(*terms: tuple[str, str, str, str]) -> IRIf:
    first, *rest = terms
    return IRIf(
        left=first[1],
        operator=first[2],
        right=first[3],
        extra_terms=tuple(IRConditionTerm(c, left, op, r) for c, left, op, r in rest),
    )


def _emit(instr: IRIf, depth: int = 0):
    diags: list = []
    return emit_if(instr, depth, diags), diags


# --- 1. simple IF unchanged ---------------------------------------------


def test_simple_if_is_unchanged():
    lines, diags = _emit(IRIf(left="WS-COUNT", operator=">", right="0"))
    assert lines == ["if (wsCount > 0) {"]
    assert diags == []


# --- 2-4. AND / OR / ordering / precedence --------------------------------


def test_and_extra_term_is_emitted():
    lines, _ = _emit(_if(("", "WS-A", ">", "5"), ("AND", "WS-B", "<", "2")))
    assert lines == ["if (wsA > 5 && wsB < 2) {"]


def test_or_extra_term_is_emitted():
    lines, _ = _emit(_if(("", "WS-A", ">", "5"), ("OR", "WS-B", "<", "2")))
    assert lines == ["if (wsA > 5 || wsB < 2) {"]


def test_multiple_terms_keep_order():
    three_and = _if(
        ("", "WS-A", ">", "5"), ("AND", "WS-B", "<", "2"), ("AND", "WS-C", "==", "3")
    )
    assert _emit(three_and)[0] == ["if (wsA > 5 && wsB < 2 && wsC == 3) {"]
    three_or = _if(
        ("", "WS-C", "==", "3"), ("OR", "WS-A", ">", "5"), ("OR", "WS-B", "<", "2")
    )
    assert _emit(three_or)[0] == ["if (wsC == 3 || wsA > 5 || wsB < 2) {"]


def test_and_binds_tighter_than_or_and_is_parenthesised():
    a_and_b_or_c = _if(
        ("", "WS-A", ">", "5"), ("AND", "WS-B", "<", "2"), ("OR", "WS-C", "==", "3")
    )
    assert _emit(a_and_b_or_c)[0] == ["if ((wsA > 5 && wsB < 2) || wsC == 3) {"]
    a_or_b_and_c = _if(
        ("", "WS-A", ">", "5"), ("OR", "WS-B", "<", "2"), ("AND", "WS-C", "==", "3")
    )
    assert _emit(a_or_b_and_c)[0] == ["if (wsA > 5 || (wsB < 2 && wsC == 3)) {"]


def test_indentation_depth_is_kept():
    lines, _ = _emit(_if(("", "WS-A", ">", "5"), ("OR", "WS-B", "<", "2")), depth=2)
    assert lines == ["        if (wsA > 5 || wsB < 2) {"]


# --- fail safe: never a partial condition -------------------------------------


@pytest.mark.parametrize(
    ("terms", "needle"),
    [
        ((("", "WS-A", ">", "5"), ("OR", "WS-B", "GREATER", "2")), "GREATER"),
        ((("", "WS-A", ">", "5"), ("OR", "", "<", "2")), "empty left operand"),
        ((("", "WS-A", ">", "5"), ("OR", "WS-B", "<", "")), "empty right operand"),
        ((("", "WS-A", ">", "5"), ("XOR", "WS-B", "<", "2")), "XOR"),
        ((("", "WS-A", "IS-TRUE", "WS-A"), ("OR", "WS-B", "<", "2")), "IS-TRUE"),
    ],
)
def test_untranslatable_term_skips_the_whole_header_with_be007(terms, needle):
    lines, diags = _emit(_if(*terms))
    assert lines == []  # never `if (wsA > 5) {` with the OR term missing
    assert [d.code for d in diags] == ["BE007"]
    assert needle in diags[0].message


# --- pipeline -----------------------------------------------------------------

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


def _java_if_lines(tmp_path, condition: str) -> list[str]:
    path = tmp_path / "t.cbl"
    path.write_text(
        _HEADER
        + f"    IF {condition}\n        MOVE 'Y' TO WS-R\n    END-IF.\n    STOP RUN.\n",
        encoding="utf-8",
    )
    java = AnalysisService().analyze_file(path).java_source
    return [ln.strip() for ln in java.splitlines() if ln.strip().startswith("if ")]


def test_pipeline_or_condition_keeps_both_sides(tmp_path):
    assert _java_if_lines(tmp_path, "WS-A > 5 OR WS-B < 2") == [
        "if (wsA > 5 || wsB < 2) {"
    ]


def test_pipeline_and_condition_keeps_both_sides(tmp_path):
    assert _java_if_lines(tmp_path, "WS-A > 5 AND WS-B < 2") == [
        "if (wsA > 5 && wsB < 2) {"
    ]


def test_pipeline_mixed_chain_keeps_every_term_and_precedence(tmp_path):
    assert _java_if_lines(tmp_path, "WS-A > 5 AND WS-B < 2 OR WS-C >= 3") == [
        "if ((wsA > 5 && wsB < 2) || wsC >= 3) {"
    ]


def test_pipeline_plain_if_is_unchanged(tmp_path):
    assert _java_if_lines(tmp_path, "WS-A > 5") == ["if (wsA > 5) {"]


# --- real corpus ----------------------------------------------------------------
#
# Whole-program Java never contains these real IFs: the backend emits only the
# entry paragraph's body and stubs every PERFORM'd paragraph (``BE009``), and all
# 11 real compound IFs live in PERFORM'd paragraphs. So the real-corpus check
# runs ``emit_if`` on the *real* ``IRIf`` instructions the real pipeline built.


@pytest.fixture(scope="module")
def real_headers():
    cache: dict[str, dict[int, tuple[list[str], list]]] = {}

    def load(filename: str) -> dict[int, tuple[list[str], list]]:
        """``{source line of the IF: (java header lines, diagnostics)}``."""
        if filename not in cache:
            result = AnalysisService().analyze_file(SOURCES / filename)
            headers: dict[int, tuple[list[str], list]] = {}
            for module in result.ir.modules:
                for fn in module.functions:
                    for block in fn.blocks:
                        for instr in block.instructions:
                            if isinstance(instr, IRIf) and instr.extra_terms:
                                diags: list = []
                                lines = emit_if(instr, 0, diags)
                                headers[instr.source_position.line] = (lines, diags)
            cache[filename] = headers
        return cache[filename]

    return load


def test_real_or_condition_driver_age_reaches_java(real_headers):
    """``IF DRIVER-AGE < 21 OR DRIVER-AGE > 75`` (insurance_claim.cbl:40) -- the
    real OR whose two operators the backend supports."""
    lines, diags = real_headers("insurance_claim.cbl")[40]
    assert lines == ["if (driverAge < 21 || driverAge > 75) {"]
    assert diags == []


def test_real_and_conditions_reach_java(real_headers):
    assert real_headers("account_eligibility.cbl")[67][0] == [
        "if (existingAccounts >= 3 && annualIncome > 75000.00) {"
    ]
    credit = real_headers("credit_approval.cbl")
    assert credit[40][0] == ["if (creditScore >= 740 && dtiPercentage <= 35.00) {"]
    assert credit[43][0] == ["if (creditScore >= 660 && dtiPercentage <= 45.00) {"]


def test_real_level88_compound_if_is_skipped_never_emitted_partially(real_headers):
    """condition_names_88.cbl:54 ``IF PHYSICAL-BRANCH AND TX-WITHDRAWAL`` uses the
    level-88 ``IS-TRUE`` sentinel, which the backend cannot translate: the header
    is skipped with ``BE007`` and must never appear with only some terms. (The six
    real compound IFs that were skipped only for ``=`` now emit -- see
    ``test_java_if_emission_fix.py``.)"""
    lines, diags = real_headers("condition_names_88.cbl")[54]
    assert lines == []
    assert [d.code for d in diags] == ["BE007"]
