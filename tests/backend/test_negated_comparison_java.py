"""
Negated relational operators propagated to Java (Stage 25).

Purpose:
    Stage 25's parser fix (``tests/parser/test_negated_comparison_operators.py``)
    makes ``IF X NOT = 'A'`` and ``IF X <> 'A'`` parse -- both collapse to the
    AST-level operator ``<>``. This file verifies that operator's *complete*
    propagation through the rest of the pipeline: the Java backend aliases
    ``<>`` to ``!=`` (``control_flow_emitter.OPERATOR_ALIASES``) exactly the
    way ``=`` is already aliased to ``==``, so it reaches the *same*,
    already-tested (Stage 24) translation -- ``_cobolEquals`` for text,
    plain ``!=`` for numbers -- with no new backend logic. It also compiles
    and *executes* the generated Java against an independent Python oracle,
    and confirms the one real corpus source whose fix reaches actual
    generated Java (``t_batch_acct_update`` -- the other three affected
    sources' fixed ``IF``s sit in code already unreachable after an
    unconditional ``GOBACK``, a pre-existing, unrelated fact; see
    docs/MMIM_NEGATED_COMPARISON_FIX.md §5) behaves exactly like COBOL when
    driven with a *distinct* ``String`` object -- the same class of defect
    Stage 24 fixed for plain ``=``.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.condition_context import (
    COBOL_EQUALS,
    COBOL_EQUALS_HELPER,
    ConditionContext,
)
from app.backend.java.control_flow_emitter import (
    OPERATOR_ALIASES,
    SUPPORTED_OPERATORS,
    emit_if,
    emit_perform_until,
)
from app.ir.instructions import IRConditionTerm, IRIf, IRPerformUntil

SOURCES = Path("data/sources/phase6-v2")

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)

_TEXT_CTX = ConditionContext(field_types={"wsCode": "String", "wsOther": "String"})
_NUM_CTX = ConditionContext(field_types={"wsN": "int"})


# ===========================================================================
# 1. ``<>`` is aliased exactly like ``=``, and reaches Stage 24's translation
# ===========================================================================


def test_neq_alias_is_registered_alongside_the_equals_alias() -> None:
    assert OPERATOR_ALIASES["="] == "=="
    assert OPERATOR_ALIASES["<>"] == "!="
    assert OPERATOR_ALIASES["<>"] in SUPPORTED_OPERATORS


def test_emit_if_angle_bracket_neq_on_text_uses_cobol_equality() -> None:
    cond = IRIf(left="WS-CODE", operator="<>", right="'AUTO'")
    assert emit_if(cond, 0, [], _TEXT_CTX) == ['if (!_cobolEquals(wsCode, "AUTO")) {']


def test_emit_if_angle_bracket_neq_without_context_is_the_old_plain_output() -> None:
    """No context (every hand-built-IR caller that predates Stage 24) still
    gets the un-aliased-to-cobolEquals, but now at least *compilable*, ``!=``."""
    cond = IRIf(left="WS-CODE", operator="<>", right="'AUTO'")
    assert emit_if(cond, 0, []) == ['if (wsCode != "AUTO") {']


def test_emit_if_angle_bracket_neq_on_numbers_is_plain_neq() -> None:
    cond = IRIf(left="WS-N", operator="<>", right="5")
    assert emit_if(cond, 0, [], _NUM_CTX) == ["if (wsN != 5) {"]


def test_perform_until_angle_bracket_neq() -> None:
    instr = IRPerformUntil(left="WS-CODE", operator="<>", right="'AUTO'")
    assert emit_perform_until(instr, 0, [], _TEXT_CTX) == [
        'while (!(!_cobolEquals(wsCode, "AUTO"))) {'
    ]


def test_compound_condition_mixing_neq_and_ordinary_terms() -> None:
    cond = IRIf(
        left="WS-CODE",
        operator="<>",
        right="'AUTO'",
        extra_terms=(
            IRConditionTerm(connector="AND", left="WS-N", operator="<>", right="5"),
        ),
    )
    ctx = ConditionContext(field_types={"wsCode": "String", "wsN": "int"})
    assert emit_if(cond, 0, [], ctx) == [
        'if (!_cobolEquals(wsCode, "AUTO") && wsN != 5) {'
    ]


def test_an_unsupported_operator_is_still_rejected_not_guessed() -> None:
    diags: list = []
    assert (
        emit_if(IRIf(left="WS-N", operator="~=", right="5"), 0, diags, _NUM_CTX) == []
    )
    assert [d.code for d in diags] == ["BE007"]


# ===========================================================================
# 2. Whole pipeline: parser -> AST -> IR -> Java, for a synthetic program
# ===========================================================================

_DATA = [
    "01  WS-CODE  PIC X(4) VALUE 'AUTO'.",
    "01  WS-OTHER PIC X(4) VALUE 'AUTO'.",
    "01  WS-N     PIC 9(3) VALUE 5.",
    "01  R01 PIC X(1) VALUE 'N'.",
    "01  R02 PIC X(1) VALUE 'N'.",
    "01  R03 PIC X(1) VALUE 'N'.",
    "01  R04 PIC X(1) VALUE 'N'.",
    "01  R05 PIC X(1) VALUE 'N'.",
]
_PROC = [
    "IF WS-CODE NOT = 'AUTO' MOVE 'Y' TO R01 END-IF",
    "IF WS-CODE <> 'AUTO' MOVE 'Y' TO R02 END-IF",
    "IF WS-N NOT = 5 MOVE 'Y' TO R03 END-IF",
    "IF WS-CODE NOT = WS-OTHER MOVE 'Y' TO R04 END-IF",
    "IF WS-CODE NOT = 'AUTO' AND WS-N NOT = 5 MOVE 'Y' TO R05 END-IF",
]


def _program(data: list[str], proc: list[str]) -> str:
    return (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. NEGJAVA.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        + "".join(f"       {line}\n" for line in data)
        + "       PROCEDURE DIVISION.\n       MAIN-PARA.\n"
        + "".join(f"           {line}\n" for line in proc)
        + "           STOP RUN.\n"
    )


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "negjava.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def test_generated_java_uses_cobol_equality_for_every_form(tmp_path) -> None:
    result = _analyse(_program(_DATA, _PROC), tmp_path)
    java = result.java_source
    assert not [d for d in result.backend_diagnostics if d.code == "BE007"]
    assert '!_cobolEquals(wsCode, "AUTO")' in java  # NOT = and <> both land here
    assert "!_cobolEquals(wsCode, wsOther)" in java
    assert "wsN != 5" in java
    assert java.count(f"static boolean {COBOL_EQUALS}(") == 1
    assert java.count("{") == java.count("}")
    assert not re.search(r'(?:==) "', java)  # never a stray identity comparison


# ===========================================================================
# 3. Executed Java against an independent oracle
# ===========================================================================

_HARNESS = """\
import java.lang.reflect.Field;
public class H {
    public static void main(String[] a) throws Exception {
        Class<?> c = Class.forName(a[0]);
        Object o = c.getDeclaredConstructor().newInstance();
        if (a.length > 1) {
            Field f = c.getDeclaredField("wsCode"); f.setAccessible(true);
            f.set(o, new String(a[1]));  // a NEW String object, never the interned literal
        }
        if (a.length > 2) {
            Field f = c.getDeclaredField("wsOther"); f.setAccessible(true);
            f.set(o, new String(a[2]));
        }
        if (a.length > 3) {
            Field f = c.getDeclaredField("wsN"); f.setAccessible(true);
            f.setInt(o, Integer.parseInt(a[3]));
        }
        c.getMethod("run").invoke(o);
        for (String n : new String[]{"r01", "r02", "r03", "r04", "r05"}) {
            Field f = c.getDeclaredField(n); f.setAccessible(true);
            System.out.println(n + "=" + f.get(o));
        }
    }
}
"""


def _cobol_text_equal(a: str, b: str) -> bool:
    return a.rstrip(" ") == b.rstrip(" ")


def _oracle(code: str, other: str, n: int) -> dict[str, str]:
    checks = [
        not _cobol_text_equal(code, "AUTO"),
        not _cobol_text_equal(code, "AUTO"),
        n != 5,
        not _cobol_text_equal(code, other),
        (not _cobol_text_equal(code, "AUTO")) and (n != 5),
    ]
    return {f"r{i:02d}": ("Y" if hit else "N") for i, hit in enumerate(checks, 1)}


@needs_java
@pytest.mark.parametrize(
    ("code", "other", "n"),
    [
        pytest.param(
            "AUTO", "AUTO", 5, id="equal-strings-distinct-objects-numeric-equal"
        ),
        pytest.param("LIFE", "AUTO", 5, id="different-code"),
        pytest.param("AUTO", "LIFE", 5, id="code-matches-literal-not-other-field"),
        pytest.param("AUTO", "AUTO", 7, id="numeric-differs"),
        pytest.param("AUTO  ", "AUTO", 5, id="trailing-spaces-not-significant"),
    ],
)
def test_executed_java_matches_cobol_for_every_negated_form(
    tmp_path, code, other, n
) -> None:
    result = _analyse(_program(_DATA, _PROC), tmp_path)
    cls = re.search(r"\bclass\s+(\w+)", result.java_source).group(1)  # type: ignore[union-attr]
    d = tmp_path / "jrun"
    d.mkdir()
    (d / f"{cls}.java").write_text(result.java_source, encoding="utf-8")
    (d / "H.java").write_text(_HARNESS, encoding="utf-8")
    comp = subprocess.run(
        ["javac", "H.java", f"{cls}.java"], cwd=d, capture_output=True, text=True
    )
    assert comp.returncode == 0, comp.stderr
    run = subprocess.run(
        ["java", "H", cls, code, other, str(n)], cwd=d, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    state = dict(line.split("=", 1) for line in run.stdout.split("\n") if "=" in line)
    assert state == _oracle(code, other, n)


# ===========================================================================
# 4. The real corpus source whose fix reaches generated Java
# ===========================================================================


@pytest.fixture(scope="module")
def batch_acct_update():
    return AnalysisService().analyze_file(SOURCES / "batch_acct_update.cbl")


def test_real_source_generates_cobol_equality_for_its_not_equal_check(
    batch_acct_update,
) -> None:
    java = batch_acct_update.java_source
    assert 'if (!_cobolEquals(wsFileStatus, "00")) {' in java
    assert java.count(f"static boolean {COBOL_EQUALS}(") == 1
    assert java.count("{") == java.count("}")
    assert not [d for d in batch_acct_update.backend_diagnostics if d.code == "BE007"]


def test_real_source_whole_class_now_compiles(batch_acct_update) -> None:
    """``batch_acct_update.cbl`` was one of the 4 corpus sources that never
    compiled, at the time this stage's own fix was written (a then-unrelated
    FILE SECTION gap: ``3100-APPLY-ACCOUNT-RULES`` -- reachable in this
    source only because a *different*, pre-existing, unrelated parser gap
    (an out-of-line ``PERFORM ... UNTIL <paragraph>`` drops the entry
    paragraph's ``GOBACK``, docs/MMIM_NEGATED_COMPARISON_FIX.md §5) --
    referenced ``FD-ACCT-BAL``/``FD-OVERDRAFT-PROT``, which the backend
    never declared as fields). **Resolved in task #stage27**
    (docs/MMIM_FILE_SECTION_FIELDS_FIX.md): FILE SECTION records are now
    parsed and their fields declared like any other, so the whole class
    compiles today. The next test still extracts and executes just the
    real ``WS-FILE-STATUS NOT = '00'`` condition in its own minimal
    wrapper -- that proof does not depend on the rest of the class and is
    kept as-is, independent of this fix."""
    if shutil.which("javac") is None:
        pytest.skip("javac not available")
    java = batch_acct_update.java_source
    cls = re.search(r"\bclass\s+(\w+)", java).group(1)  # type: ignore[union-attr]
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / f"{cls}.java").write_text(java, encoding="utf-8")
        comp = subprocess.run(
            ["javac", f"{cls}.java"], cwd=work, capture_output=True, text=True
        )
    assert comp.returncode == 0, comp.stderr


@needs_java
@pytest.mark.parametrize(
    ("status", "expect_eof"),
    [
        pytest.param("00", False, id="status-00-not-eof"),
        pytest.param("00  ", False, id="status-00-padded-still-not-eof"),
        pytest.param("35", True, id="status-35-is-eof"),
        pytest.param(None, True, id="never-set-status-is-eof"),
    ],
)
def test_real_condition_extracted_and_executed_matches_cobol(
    batch_acct_update, tmp_path, status, expect_eof
) -> None:
    """Rather than compiling the whole (pre-existingly non-compiling, see
    above) class, extract the *real* ``IRIf`` for ``WS-FILE-STATUS NOT =
    '00'`` from the real corpus source's own IR and translate it with the
    real ``emit_if`` -- proving this stage's fix on the actual backend
    output for the actual real-corpus instruction, not a re-typed stand-in
    -- then embed that one real, translated line in a small class carrying
    only the two real fields it needs. Every status here is delivered as a
    *distinct* ``String`` object -- exactly what defeated Java ``==`` before
    Stage 24, and what a ``NOT =``/``<>`` implementation that fell back to
    plain ``!=`` on ``String`` references would still get wrong for the
    padded case."""
    ir_if = next(
        i
        for i in batch_acct_update.ir.modules[0].functions[0].blocks[0].instructions
        if type(i).__name__ == "IRIf" and i.left == "WS-FILE-STATUS"
    )
    assert ir_if.operator == "<>"  # this stage's fix: was unparseable before it
    ctx = ConditionContext(
        field_types={"wsFileStatus": "String", "wsEofFlag": "String"}
    )
    (condition_line,) = emit_if(ir_if, 0, [], ctx)
    assert condition_line == 'if (!_cobolEquals(wsFileStatus, "00")) {'

    java_class = (
        "public class R {\n"
        "    private String wsFileStatus;\n"
        '    private String wsEofFlag = "N";\n'
        "    public void run() {\n"
        f"        {condition_line}\n"
        '            wsEofFlag = "Y";\n'
        "        }\n"
        "    }\n"
        "    public static void main(String[] a) throws Exception {\n"
        "        Object o = new R();\n"
        "        if (a.length > 0) {\n"
        '            java.lang.reflect.Field f = R.class.getDeclaredField("wsFileStatus");\n'
        "            f.setAccessible(true);\n"
        "            f.set(o, new String(a[0]));\n"
        "        }\n"
        "        ((R) o).run();\n"
        '        java.lang.reflect.Field f = R.class.getDeclaredField("wsEofFlag");\n'
        "        f.setAccessible(true);\n"
        "        System.out.println(f.get(o));\n"
        "    }\n" + "\n".join(COBOL_EQUALS_HELPER) + "\n}\n"
    )
    (tmp_path / "R.java").write_text(java_class, encoding="utf-8")
    comp = subprocess.run(
        ["javac", "R.java"], cwd=tmp_path, capture_output=True, text=True
    )
    assert comp.returncode == 0, comp.stderr
    args = ["java", "R"] + ([status] if status is not None else [])
    out = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    result_flag = out.stdout.strip()
    assert (result_flag == "Y") == expect_eof, (status, result_flag)


def test_real_corpus_all_four_not_equal_sources_no_longer_omit_their_condition() -> (
    None
):
    """None of the four sources' now-parseable comparisons is silently missing
    from generated Java or business rules -- see
    tests/parser/test_negated_comparison_operators.py for the parse-level
    checks; this only confirms none of them regresses to a BE007 omission."""
    for filename in (
        "account_eligibility",
        "batch_acct_update",
        "insurance_claim",
        "payment_gateway",
    ):
        result = AnalysisService().analyze_file(SOURCES / f"{filename}.cbl")
        assert not [
            d
            for d in result.backend_diagnostics
            if d.code == "BE007"
            and "IS-TRUE" not in d.message
            and "IS-FALSE" not in d.message
        ]
