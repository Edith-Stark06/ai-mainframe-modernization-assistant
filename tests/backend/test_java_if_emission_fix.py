"""Java emission of COBOL ``=`` and of an untranslatable IF/PERFORM UNTIL header.

Two defects found by the ``mmim-gen-v11`` audit, both in the Java backend:

1. ``control_flow_emitter.SUPPORTED_OPERATORS`` is ``== != > >= < <=`` but the
   parser and IR builder pass COBOL's own equality operator ``=`` through
   unchanged, so *every* ``IF``/``PERFORM UNTIL`` using ``=`` -- the most common
   COBOL comparison -- was rejected with ``BE007``. ``=`` is now emitted as Java
   ``==``. (``SUPPORTED_OPERATORS`` itself is unchanged; the COBOL spelling is
   an alias in ``OPERATOR_ALIASES``.)

2. When a header could not be translated, ``_collect_statements`` still opened a
   depth level, so the guarded body and the closing ``}`` were emitted without
   their ``if (...) {``: unbalanced Java or, had it balanced, guarded statements
   that run unconditionally. The whole construct (header, ``ELSE`` branch, body,
   nested constructs, closer) is now omitted and replaced by one ``// TODO``
   comment.

Out of scope and untouched: COBOL's single-quoted literals (``'Y'``) are
translated as identifiers by ``_translate_operand`` (``== y``); that is a
separate pre-existing defect, so the tests assert the operator and structure,
never a single-quoted literal's translation.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.control_flow_emitter import (
    OPERATOR_ALIASES,
    SUPPORTED_OPERATORS,
    emit_if,
    emit_perform_until,
)
from app.backend.java.generator import generate_with_diagnostics
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRConditionTerm,
    IRDisplay,
    IRElse,
    IREndIf,
    IREndPerform,
    IRIf,
    IRPerformUntil,
)
from app.ir.program import IRFunction, IRModule, IRProgram

SOURCES = Path("data/sources/phase6-v2")


def _program(*instructions) -> IRProgram:
    block = IRBasicBlock(label="entry", instructions=instructions)
    func = IRFunction(name="__entry__", blocks=(block,))
    return IRProgram(name="T", modules=(IRModule(name="T", functions=(func,)),))


def _main(src: str) -> str:
    """Just the generated ``run()`` body, where the control flow lives."""
    return src.split("public void run() {", 1)[1]


def _balanced(src: str) -> bool:
    return src.count("{") == src.count("}")


# --- defect 1: COBOL '=' -> Java '==' -------------------------------------------


def test_operator_sets_are_as_documented():
    assert SUPPORTED_OPERATORS == {"==", "!=", ">", ">=", "<", "<="}  # unchanged
    # "<>" (task #stage25, docs/MMIM_NEGATED_COMPARISON_FIX.md): COBOL's own
    # "not equal" spelling, aliased to Java "!=" the same way "=" is aliased
    # to "==" -- see tests/backend/test_negated_comparison_java.py.
    assert OPERATOR_ALIASES == {"=": "==", "<>": "!="}


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("WS-A", "5", "if (wsA == 5) {"),
        ("WS-A", "WS-B", "if (wsA == wsB) {"),
        ("WS-CODE", '"Y"', 'if (wsCode == "Y") {'),
        ("WS-RATE", "0.25", "if (wsRate == 0.25) {"),
        ("WS-T", "-1", "if (wsT == -1) {"),
    ],
)
def test_cobol_equals_becomes_java_double_equals(left, right, expected):
    diags: list = []
    assert emit_if(IRIf(left=left, operator="=", right=right), 0, diags) == [expected]
    assert diags == []


def test_double_equals_still_works_and_is_the_same_output():
    diags: list = []
    assert emit_if(IRIf(left="WS-A", operator="==", right="5"), 0, diags) == [
        "if (wsA == 5) {"
    ]
    assert diags == []


@pytest.mark.parametrize("op", [">", "<", ">=", "<=", "!="])
def test_every_other_supported_operator_is_unchanged(op):
    diags: list = []
    assert emit_if(IRIf(left="WS-A", operator=op, right="5"), 1, diags) == [
        f"    if (wsA {op} 5) {{"
    ]
    assert diags == []


@pytest.mark.parametrize("op", ["GREATER", "~=", "", "IS-TRUE", "EQUAL"])
def test_unsupported_operators_are_still_rejected(op):
    # "<>" moved out of this list (task #stage25): it is now supported, the
    # same way "=" already was -- see test_operator_sets_are_as_documented
    # and tests/backend/test_negated_comparison_java.py. "~=" (a spelling no
    # grammar in this project ever produces) keeps this parametrization's
    # original size and intent: prove an operator outside both
    # SUPPORTED_OPERATORS and OPERATOR_ALIASES is still safely rejected.
    diags: list = []
    assert emit_if(IRIf(left="WS-A", operator=op, right="5"), 0, diags) == []
    assert [d.code for d in diags] == ["BE007"]


def test_equals_in_perform_until():
    diags: list = []
    assert emit_perform_until(
        IRPerformUntil(left="WS-X", operator="=", right="5"), 0, diags
    ) == ["while (!(wsX == 5)) {"]
    assert diags == []


# --- compound conditions containing '=' -------------------------------------------


def _if(*terms: tuple[str, str, str, str]) -> IRIf:
    first, *rest = terms
    return IRIf(
        left=first[1],
        operator=first[2],
        right=first[3],
        extra_terms=tuple(IRConditionTerm(c, left, op, r) for c, left, op, r in rest),
    )


def test_compound_conditions_with_equals():
    or_ = _if(("", "WS-A", ">", "5"), ("OR", "WS-B", "=", "2"))
    assert emit_if(or_, 0, [])[0] == "if (wsA > 5 || wsB == 2) {"
    and_ = _if(("", "WS-A", "=", "5"), ("AND", "WS-B", "=", "2"))
    assert emit_if(and_, 0, [])[0] == "if (wsA == 5 && wsB == 2) {"
    mixed = _if(
        ("", "WS-A", "=", "5"), ("AND", "WS-B", "<", "2"), ("OR", "WS-C", "=", "3")
    )
    assert emit_if(mixed, 0, [])[0] == "if ((wsA == 5 && wsB < 2) || wsC == 3) {"


def test_compound_with_one_unsupported_term_is_never_truncated():
    """``IS-TRUE`` (level-88 sentinel) is still untranslatable: the whole header
    is skipped, never an ``if`` carrying only the terms that translate."""
    diags: list = []
    cond = _if(("", "WS-A", "=", "5"), ("OR", "IS-OK", "IS-TRUE", "IS-OK"))
    assert emit_if(cond, 0, diags) == []
    assert [d.code for d in diags] == ["BE007"]


_HEADER = textwrap.dedent("""\
    IDENTIFICATION DIVISION.
    PROGRAM-ID. T.
    DATA DIVISION.
    WORKING-STORAGE SECTION.
    01 WS-A PIC 9(3) VALUE 0.
    01 WS-B PIC 9(3) VALUE 0.
    01 WS-R PIC X(4) VALUE SPACE.
    01 WS-CODE PIC X VALUE SPACE.
        88 IS-OK VALUE 'A'.
        88 IS-UNSAFE VALUE ZERO.
    PROCEDURE DIVISION.
    MAIN.
""")


def _java(tmp_path, body: str):
    path = tmp_path / "t.cbl"
    path.write_text(_HEADER + body, encoding="utf-8")
    result = AnalysisService().analyze_file(path)
    return result.java_source, result.backend_diagnostics


def test_pipeline_cobol_equals_reaches_java(tmp_path):
    java, diags = _java(
        tmp_path, '    IF WS-A = 5\n        DISPLAY "X"\n    END-IF.\n    STOP RUN.\n'
    )
    assert "if (wsA == 5) {" in java
    assert not [d for d in diags if d.code == "BE007"]
    assert _balanced(java)


def test_pipeline_compound_with_equals_reaches_java(tmp_path):
    java, diags = _java(
        tmp_path,
        '    IF WS-A > 5 OR WS-B = 2\n        DISPLAY "X"\n    END-IF.\n    STOP RUN.\n',
    )
    assert "if (wsA > 5 || wsB == 2) {" in java
    assert not [d for d in diags if d.code == "BE007"]
    assert _balanced(java)


# --- defect 2: an untranslatable header must not emit its body -----------------------

_BAD = IRIf(left="WS-X", operator="IS-TRUE", right="WS-X")


def test_untranslatable_if_omits_body_and_closing_brace():
    result = generate_with_diagnostics(
        _program(
            _BAD,
            IRDisplay(operand='"GUARDED"'),
            IREndIf(),
            IRDisplay(operand='"AFTER"'),
        )
    )
    main = _main(result.source)
    assert "GUARDED" not in main  # never runs unconditionally
    assert 'System.out.println("AFTER");' in main  # generation continues
    assert "// TODO: IF condition cannot be translated (BE007)" in main
    assert _balanced(result.source)
    assert [d.code for d in result.diagnostics if d.code == "BE007"] == ["BE007"]


def test_untranslatable_if_with_else_omits_both_branches():
    result = generate_with_diagnostics(
        _program(
            _BAD,
            IRDisplay(operand='"THEN-BODY"'),
            IRElse(),
            IRDisplay(operand='"ELSE-BODY"'),
            IREndIf(),
        )
    )
    main = _main(result.source)
    assert "THEN-BODY" not in main and "ELSE-BODY" not in main
    assert "} else {" not in main
    assert _balanced(result.source)


def test_untranslatable_outer_if_omits_a_translatable_nested_if():
    good = IRIf(left="WS-A", operator=">", right="1")
    result = generate_with_diagnostics(
        _program(
            _BAD,
            good,
            IRDisplay(operand='"INNER"'),
            IREndIf(),
            IRDisplay(operand='"OUTER"'),
            IREndIf(),
            IRDisplay(operand='"AFTER"'),
        )
    )
    main = _main(result.source)
    assert "INNER" not in main and "OUTER" not in main and "wsA > 1" not in main
    assert 'System.out.println("AFTER");' in main
    assert _balanced(result.source)


def test_untranslatable_inner_if_leaves_the_translatable_outer_intact():
    good = IRIf(left="WS-A", operator="=", right="1")
    result = generate_with_diagnostics(
        _program(
            good,
            IRDisplay(operand='"BEFORE"'),
            _BAD,
            IRDisplay(operand='"HIDDEN"'),
            IREndIf(),
            IRDisplay(operand='"TAIL"'),
            IREndIf(),
        )
    )
    main = _main(result.source)
    assert "if (wsA == 1) {" in main
    assert "BEFORE" in main and "TAIL" in main
    assert "HIDDEN" not in main
    assert _balanced(result.source)
    # the surviving statements are still inside the outer if, one level deep
    lines = [ln for ln in main.splitlines() if "BEFORE" in ln or "TAIL" in ln]
    assert all(ln.startswith("            ") for ln in lines)


def test_untranslatable_perform_until_omits_its_body():
    result = generate_with_diagnostics(
        _program(
            IRPerformUntil(left="WS-X", operator="IS-TRUE", right="WS-X"),
            IRDisplay(operand='"LOOP-BODY"'),
            IREndPerform(),
            IRDisplay(operand='"AFTER"'),
        )
    )
    main = _main(result.source)
    assert "LOOP-BODY" not in main
    assert "// TODO: PERFORM UNTIL condition cannot be translated (BE007)" in main
    assert 'System.out.println("AFTER");' in main
    assert _balanced(result.source)


def test_malformed_unclosed_untranslatable_if_omits_only_its_header():
    """No matching IREndIf: nothing is left open and later statements survive
    (the pre-existing contract of ``test_generation_continues_after_bad_if``)."""
    result = generate_with_diagnostics(_program(_BAD, IRDisplay(operand='"AFTER"')))
    assert 'System.out.println("AFTER");' in result.source
    assert _balanced(result.source)


def test_translatable_if_is_unchanged():
    result = generate_with_diagnostics(
        _program(
            IRIf(left="WS-A", operator=">", right="1"),
            IRDisplay(operand='"YES"'),
            IRElse(),
            IRDisplay(operand='"NO"'),
            IREndIf(),
        )
    )
    main = _main(result.source)
    assert "if (wsA > 1) {" in main and "} else {" in main
    assert "// TODO: IF condition" not in main
    assert _balanced(result.source)


def test_pipeline_untranslatable_level88_if_never_runs_its_body(tmp_path):
    """``IS-UNSAFE`` is ``VALUE ZERO`` on an alphanumeric item: a figurative
    constant with no proven Java equivalent, so (unlike ``IS-OK``, translated
    since Stage 24) its ``IF`` is still omitted with ``BE007``, never guessed."""
    java, diags = _java(
        tmp_path,
        '    IF IS-UNSAFE\n        DISPLAY "GUARDED"\n    ELSE\n        DISPLAY "OTHER"\n'
        '    END-IF.\n    DISPLAY "AFTER".\n    STOP RUN.\n',
    )
    assert "GUARDED" not in java and "OTHER" not in java
    assert 'System.out.println("AFTER");' in java
    assert _balanced(java)
    assert any(d.code == "BE007" for d in diags)


@pytest.mark.skipif(shutil.which("javac") is None, reason="javac not installed")
def test_pipeline_output_with_an_omitted_if_compiles_with_javac(tmp_path):
    java, _ = _java(
        tmp_path,
        '    DISPLAY "START".\n    IF IS-UNSAFE\n        DISPLAY "GUARDED"\n    END-IF.\n'
        '    IF WS-A = 5\n        DISPLAY "EQ"\n    END-IF.\n    STOP RUN.\n',
    )
    (tmp_path / "T.java").write_text(java, encoding="utf-8")
    done = subprocess.run(
        ["javac", str(tmp_path / "T.java")], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr


# --- real corpus ------------------------------------------------------------------------
#
# Whole-program Java rarely contains these IFs (the backend stubs every PERFORM'd
# paragraph), so the real conditions are checked by running ``emit_if`` on the real
# ``IRIf`` instructions the real pipeline built.


@pytest.fixture(scope="module")
def real_headers():
    cache: dict[str, dict[int, tuple[list[str], list]]] = {}

    def load(filename: str) -> dict[int, tuple[list[str], list]]:
        if filename not in cache:
            result = AnalysisService().analyze_file(SOURCES / filename)
            headers: dict[int, tuple[list[str], list]] = {}
            for module in result.ir.modules:
                for fn in module.functions:
                    for block in fn.blocks:
                        for instr in block.instructions:
                            if isinstance(instr, IRIf) and instr.extra_terms:
                                diags: list = []
                                headers[instr.source_position.line] = (
                                    emit_if(instr, 0, diags),
                                    diags,
                                )
            cache[filename] = headers
        return cache[filename]

    return load


# The 6 real compound IFs that were skipped only because they contain '='
# (the 7th, condition_names_88.cbl:54, uses IS-TRUE and stays skipped).
#
# The right-hand-side placeholder is `"[^"]*"` (a Java string literal, which
# may contain spaces -- e.g. AUTH-OUT-RESP-CODE = ' ') rather than `\S+`:
# this file predates docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md, when a
# single-quoted COBOL literal still translated to a bare, space-free
# identifier (`\S+` was a safe placeholder for that broken form). These
# patterns assert *structure* (both operands present, correct connector),
# never the literal's own translated form -- that is
# test_java_literal_emission_fix.py's job.
REAL_EQUALS = [
    (
        "credit_approval.cbl",
        37,
        r'if \(bankruptcyFlag == "[^"]*" \|\| creditScore < 580\) \{',
    ),
    (
        "daily_trans_report.cbl",
        56,
        r'if \(fdTxVal > 10000\.00 \|\| fdTxSuspicious == "[^"]*"\) \{',
    ),
    (
        "insurance_claim.cbl",
        37,
        r'if \(policeReportFiled == "[^"]*" && claimAmount > 5000\.00\) \{',
    ),
    (
        "mortgage_service.cbl",
        50,
        r'if \(outCreditStatus == "[^"]*" && inLtvRatio <= 80\.00\) \{',
    ),
    (
        "payment_gateway.cbl",
        46,
        r'if \(authOutRespCode == "[^"]*" \|\| authOutRespCode == "[^"]*"\) \{',
    ),
    (
        "pricing_tier.cbl",
        69,
        r'if \(paymentMethod == "[^"]*" \|\| paymentMethod == "[^"]*"\) \{',
    ),
]


@pytest.mark.parametrize(("filename", "line", "pattern"), REAL_EQUALS)
def test_real_compound_if_with_equals_now_emits_every_term(
    real_headers, filename, line, pattern
):
    lines, diags = real_headers(filename)[line]
    assert len(lines) == 1 and re.fullmatch(pattern, lines[0]), lines
    assert diags == []


def test_real_level88_compound_if_stays_skipped(real_headers):
    lines, diags = real_headers("condition_names_88.cbl")[54]
    assert lines == []
    assert [d.code for d in diags] == ["BE007"]


def test_real_previously_supported_headers_are_unchanged(real_headers):
    assert real_headers("insurance_claim.cbl")[40][0] == [
        "if (driverAge < 21 || driverAge > 75) {"
    ]
    assert real_headers("account_eligibility.cbl")[67][0] == [
        "if (existingAccounts >= 3 && annualIncome > 75000.00) {"
    ]


def test_real_daily_trans_report_java_is_balanced_and_carries_both_terms(tmp_path):
    """``FD-TX-SUSPICIOUS`` (task #stage27, docs/MMIM_FILE_SECTION_FIELDS_FIX.md)
    is now a declared, known-``String`` FILE SECTION field, so its
    comparison against a text literal correctly gets the ``_cobolEquals``
    helper (docs/MMIM_STRING_COMPARISON_FIX.md) instead of identity ``==`` --
    the same upgrade every other known-text comparison already gets."""
    result = AnalysisService().analyze_file(SOURCES / "daily_trans_report.cbl")
    java = result.java_source
    assert _balanced(java)
    headers = [ln.strip() for ln in java.splitlines() if ln.strip().startswith("if (")]
    assert len(headers) == 1
    assert re.fullmatch(
        r'if \(fdTxVal > 10000\.00 \|\| _cobolEquals\(fdTxSuspicious, "[^"]*"\)\) \{',
        headers[0],
    )
    assert not [d for d in result.backend_diagnostics if d.code == "BE007"]


@pytest.mark.parametrize(
    "filename",
    [
        "batch_acct_update.cbl",
        "fallthrough_flow.cbl",
        "goto_spaghetti.cbl",
        "policy_redefines.cbl",
        "daily_trans_report.cbl",
    ],
)
def test_real_sources_that_were_unbalanced_are_balanced(filename):
    """These five had ``BE007``-skipped headers whose body and ``}`` were still
    emitted (unbalanced Java)."""
    java = AnalysisService().analyze_file(SOURCES / filename).java_source
    assert _balanced(java), filename
