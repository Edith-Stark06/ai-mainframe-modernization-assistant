"""
COBOL comparison semantics in the Java backend (Stage 24).

Purpose:
    Two related gaps in ``IF`` / ``PERFORM UNTIL`` translation, fixed
    separably but through one shared expression-generation path
    (``control_flow_emitter._build_condition``):

    1. **Text comparison.**  ``IF WS-CODE = 'AUTO'`` was emitted as
       ``wsCode == "AUTO"``.  Java ``==`` on ``String`` references compares
       object identity, so it held only while the field still contained its
       compile-time literal and failed for an equal string from anywhere else.
       ``=``/``!=`` between two operands that are *known text* is now COBOL's
       space-padded alphanumeric equality (``_cobolEquals``).  Numeric, mixed,
       unknown-typed and ordering comparisons are unchanged.
    2. **Level-88 condition-names.**  ``IF NAME`` / ``IF NOT NAME`` (the
       ``IS-TRUE`` / ``IS-FALSE`` IR sentinels) were always omitted with
       ``BE007``.  The AST already carries everything needed -- the parent item
       (nearest preceding non-88 item) and the declared ``VALUE``/``VALUES`` --
       so a condition is now the parent compared with each value; anything that
       cannot be translated provably correctly keeps ``BE007``.

    The strong checks *execute* the generated Java (real ``javac``/``java``)
    and compare every result field with an independent Python oracle of the COBOL
    semantics.  The oracle never reads the Java text; the seeds are equal but
    *distinct* ``String`` objects, which is exactly what defeats ``==``.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.condition_context import (
    COBOL_EQUALS,
    ConditionContext,
    ConditionName,
    build_condition_context,
    build_condition_names,
    translate_comparison,
    translate_condition_name,
)
from app.backend.java.control_flow_emitter import emit_if, emit_perform_until
from app.backend.java.field_model import JavaField
from app.backend.java.generator import generate_with_diagnostics
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRConditionTerm,
    IREndPerform,
    IRIf,
    IRMove,
    IRPerformUntil,
)
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

SOURCES = Path("data/sources/phase6-v2")

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)


def _ctx(**types: str) -> ConditionContext:
    return ConditionContext(field_types=dict(types))


# ===========================================================================
# 1. translate_comparison: which comparisons are text comparisons
# ===========================================================================


@pytest.mark.parametrize(
    ("left", "op", "right", "expected"),
    [
        # both known text -> COBOL alphanumeric equality
        ("WS-CODE", "==", "'AUTO'", '_cobolEquals(wsCode, "AUTO")'),
        ("WS-CODE", "!=", "'AUTO'", '!_cobolEquals(wsCode, "AUTO")'),
        ("'AUTO'", "==", "WS-CODE", '_cobolEquals("AUTO", wsCode)'),
        ("WS-CODE", "==", "WS-OTHER", "_cobolEquals(wsCode, wsOther)"),
        ("WS-CODE", "!=", "WS-OTHER", "!_cobolEquals(wsCode, wsOther)"),
        ("'A'", "==", "'B'", '_cobolEquals("A", "B")'),
        ("WS-CODE", "==", '"AUTO"', '_cobolEquals(wsCode, "AUTO")'),
        ("WS-CODE", "==", "'SAY \"HI\"'", '_cobolEquals(wsCode, "SAY \\"HI\\"")'),
        ("WS-GROUP", "==", "'ABC'", '_cobolEquals(wsGroup, "ABC")'),  # group = String
        # SPACES/SPACE figurative constants are text too (task #stage31):
        # a String field compared with one is a known-text comparison, same
        # as any quoted literal.
        ("WS-CODE", "==", "SPACES", '_cobolEquals(wsCode, "")'),
        ("WS-CODE", "!=", "SPACES", '!_cobolEquals(wsCode, "")'),
        ("SPACES", "==", "WS-CODE", '_cobolEquals("", wsCode)'),
        ("WS-CODE", "==", "SPACE", '_cobolEquals(wsCode, "")'),
    ],
)
def test_known_text_equality_is_a_cobol_comparison(left, op, right, expected) -> None:
    ctx = _ctx(wsCode="String", wsOther="String", wsGroup="String")
    assert translate_comparison(left, op, right, ctx) == expected


@pytest.mark.parametrize(
    ("left", "op", "right"),
    [
        # numeric
        ("WS-N", "==", "5"),
        ("WS-N", "!=", "5"),
        ("WS-AMT", "==", "2.50"),
        ("WS-N", "==", "WS-AMT"),
        # mixed text / numeric -> not guessed
        ("WS-CODE", "==", "5"),
        ("WS-N", "==", "'A'"),
        ("WS-CODE", "==", "WS-N"),
        # one side of unknown type (a FILE SECTION field)
        ("FD-FLAG", "==", "'Y'"),
        ("'Y'", "==", "FD-FLAG"),
        ("FD-A", "==", "FD-B"),
        # ZERO-family figurative constants are numeric, not text (task
        # #stage31: SPACES/SPACE moved to the "known text" list above;
        # ZERO/ZEROS/ZEROES against a *text* field is a type mismatch this
        # module still declines to guess at)
        ("WS-CODE", "==", "ZEROS"),
        ("ZERO", "==", "WS-CODE"),
        # ordering is not translated (collating-sequence semantics)
        ("WS-CODE", ">", "'A'"),
        ("WS-CODE", "<=", "WS-OTHER"),
        ("WS-CODE", ">=", "'A'"),
    ],
)
def test_everything_else_is_left_to_the_unchanged_translation(left, op, right) -> None:
    ctx = _ctx(wsCode="String", wsOther="String", wsN="int", wsAmt="double")
    assert translate_comparison(left, op, right, ctx) is None


def test_no_context_means_no_change() -> None:
    assert translate_comparison("WS-CODE", "==", "'A'", None) is None
    assert translate_comparison("WS-CODE", "==", "'A'", ConditionContext()) is None


# ===========================================================================
# 2. The emitter: same path serves IF, compound IF and PERFORM UNTIL
# ===========================================================================

_TYPES = _ctx(wsCode="String", wsFlag="String", wsN="int")


def test_emit_if_text_equality_and_inequality() -> None:
    eq = IRIf(left="WS-CODE", operator="=", right="'AUTO'")  # COBOL spelling
    assert emit_if(eq, 0, [], _TYPES) == ['if (_cobolEquals(wsCode, "AUTO")) {']
    ne = IRIf(left="WS-CODE", operator="!=", right="'AUTO'")
    assert emit_if(ne, 1, [], _TYPES) == ['    if (!_cobolEquals(wsCode, "AUTO")) {']


def test_emit_if_without_a_context_is_byte_for_byte_the_old_output() -> None:
    eq = IRIf(left="WS-CODE", operator="=", right="'AUTO'")
    assert emit_if(eq, 0, []) == ['if (wsCode == "AUTO") {']
    assert emit_if(IRIf(left="WS-A", operator="==", right="WS-B"), 0, []) == [
        "if (wsA == wsB) {"
    ]


def test_emit_if_numeric_and_unrelated_conditions_unchanged_with_a_context() -> None:
    cases = [
        (IRIf(left="WS-N", operator="=", right="5"), "if (wsN == 5) {"),
        (IRIf(left="WS-N", operator=">=", right="5"), "if (wsN >= 5) {"),
        (IRIf(left="WS-CODE", operator=">", right="'A'"), 'if (wsCode > "A") {'),
        (IRIf(left="WS-CODE", operator="=", right="5"), "if (wsCode == 5) {"),
        (IRIf(left="FD-X", operator="=", right="'Y'"), 'if (fdX == "Y") {'),
    ]
    for instr, expected in cases:
        assert emit_if(instr, 0, [], _TYPES) == [expected], instr


def test_compound_if_translates_each_term_on_its_own_type() -> None:
    cond = IRIf(
        left="WS-CODE",
        operator="=",
        right="'AUTO'",
        extra_terms=(
            IRConditionTerm(connector="AND", left="WS-N", operator=">", right="3"),
            IRConditionTerm(connector="OR", left="WS-FLAG", operator="!=", right="'Y'"),
        ),
    )
    assert emit_if(cond, 0, [], _TYPES) == [
        'if ((_cobolEquals(wsCode, "AUTO") && wsN > 3) || !_cobolEquals(wsFlag, "Y")) {'
    ]


def test_perform_until_uses_the_same_translation() -> None:
    instr = IRPerformUntil(left="WS-FLAG", operator="=", right="'Y'")
    assert emit_perform_until(instr, 0, [], _TYPES) == [
        'while (!(_cobolEquals(wsFlag, "Y"))) {'
    ]
    assert emit_perform_until(instr, 0, []) == ['while (!(wsFlag == "Y")) {']


# ===========================================================================
# 3. Level-88: which conditions can be translated, and how
# ===========================================================================


def _names(**entries: tuple[str, tuple[str, ...]]) -> dict[str, ConditionName]:
    return {
        n: ConditionName(n, parent, values) for n, (parent, values) in entries.items()
    }


def _cond_ctx(types: dict[str, str], names) -> ConditionContext:
    return ConditionContext(field_types=types, condition_names=names)


_TYPES88 = {"wsType": "String", "wsLvl": "int", "wsRate": "double"}
_NAMES88 = _names(
    **{
        "IS-DEP": ("WS-TYPE", ("'D'",)),
        "IS-KNOWN": ("WS-TYPE", ("'D'", "'W'", "'T'")),
        "IS-BLANK": ("WS-TYPE", ("SPACES",)),
        "IS-NEG": ("WS-LVL", ("-1",)),
        "IS-SMALL": ("WS-LVL", ("-1", "0", "+1")),
        "IS-ZERO": ("WS-LVL", ("ZERO",)),
        "IS-PAD": ("WS-LVL", ("007",)),  # octal-looking literal
        "IS-HALF": ("WS-RATE", (".5",)),
        "IS-NEGHALF": ("WS-RATE", ("-.5",)),
        "IS-RATES": ("WS-RATE", ("0.50", "-0.50", "2.25")),
    }
)


@pytest.mark.parametrize(
    ("name", "holds", "expected"),
    [
        ("IS-DEP", True, '_cobolEquals(wsType, "D")'),
        ("IS-DEP", False, '!_cobolEquals(wsType, "D")'),
        (
            "IS-KNOWN",
            True,
            '(_cobolEquals(wsType, "D") || _cobolEquals(wsType, "W") '
            '|| _cobolEquals(wsType, "T"))',
        ),
        (
            "IS-KNOWN",
            False,
            '(!_cobolEquals(wsType, "D") && !_cobolEquals(wsType, "W") '
            '&& !_cobolEquals(wsType, "T"))',
        ),
        ("IS-BLANK", True, '_cobolEquals(wsType, "")'),
        ("IS-NEG", True, "wsLvl == -1"),
        ("IS-NEG", False, "wsLvl != -1"),
        ("IS-SMALL", True, "(wsLvl == -1 || wsLvl == 0 || wsLvl == 1)"),
        ("IS-SMALL", False, "(wsLvl != -1 && wsLvl != 0 && wsLvl != 1)"),
        ("IS-ZERO", True, "wsLvl == 0"),
        ("IS-PAD", True, "wsLvl == 7"),  # 007 is 7, never octal
        ("IS-HALF", True, "wsRate == 0.5"),
        ("IS-NEGHALF", True, "wsRate == -0.5"),
        ("IS-RATES", True, "(wsRate == 0.50 || wsRate == -0.50 || wsRate == 2.25)"),
    ],
)
def test_translatable_condition_names(name, holds, expected) -> None:
    ctx = _cond_ctx(_TYPES88, _NAMES88)
    assert translate_condition_name(name, holds, ctx) == (expected, "")


@pytest.mark.parametrize(
    ("entry", "parent_type", "why"),
    [
        (("P", ("ZERO",)), "String", "no proven Java equivalent"),  # ZERO on text
        (("P", ("HIGH-VALUES",)), "String", "no proven Java equivalent"),
        (("P", ("LOW-VALUE",)), "int", "no proven Java equivalent"),
        (
            ("P", ("'X'",)),
            "int",
            "no proven Java equivalent",
        ),  # text value, number parent
        (("P", ("SPACES",)), "int", "no proven Java equivalent"),
        (
            ("P", ("1",)),
            "String",
            "no proven Java equivalent",
        ),  # number value, text parent
        (("P", (".5",)), "int", "no proven Java equivalent"),  # decimal, integer parent
        (("P", ("9999999999",)), "int", "no proven Java equivalent"),  # int overflow
        (("P", ("'A'", "1")), "String", "no proven Java equivalent"),  # one bad value
    ],
)
def test_untranslatable_condition_names_report_a_reason(
    entry, parent_type, why
) -> None:
    parent, values = entry
    ctx = _cond_ctx({"p": parent_type}, _names(C=(parent, values)))
    expression, reason = translate_condition_name("C", True, ctx)
    assert expression is None and why in reason
    # and the emitter turns that into BE007 + an omitted IF
    diags: list[Any] = []
    assert emit_if(IRIf(left="C", operator="IS-TRUE", right="C"), 0, diags, ctx) == []
    assert [d.code for d in diags] == ["BE007"]


def test_condition_name_with_an_undeclared_or_unsupported_parent_is_not_translated() -> (
    None
):
    ctx = _cond_ctx({}, _names(C=("MISSING", ("'A'",))))
    expression, reason = translate_condition_name("C", True, ctx)
    assert expression is None and "not a declared field" in reason
    ctx = _cond_ctx({"p": "boolean"}, _names(C=("P", ("'A'",))))
    assert translate_condition_name("C", True, ctx)[0] is None


def test_an_unknown_condition_name_keeps_the_original_be007_message() -> None:
    diags: list[Any] = []
    instr = IRIf(left="NOPE", operator="IS-TRUE", right="NOPE")
    assert emit_if(instr, 0, diags, _cond_ctx(_TYPES88, _NAMES88)) == []
    assert emit_if(instr, 0, [], None) == []  # no context at all: unchanged
    assert [d.code for d in diags] == ["BE007"]
    assert "unsupported operator 'IS-TRUE'" in diags[0].message


def test_condition_name_in_compound_and_perform_until() -> None:
    ctx = _cond_ctx(dict(_TYPES88, wsN="int"), _NAMES88)
    cond = IRIf(
        left="IS-DEP",
        operator="IS-TRUE",
        right="IS-DEP",
        extra_terms=(
            IRConditionTerm(
                connector="AND", left="IS-NEG", operator="IS-FALSE", right="IS-NEG"
            ),
            IRConditionTerm(connector="OR", left="WS-N", operator="=", right="1"),
        ),
    )
    assert emit_if(cond, 0, [], ctx) == [
        'if ((_cobolEquals(wsType, "D") && wsLvl != -1) || wsN == 1) {'
    ]
    until = IRPerformUntil(left="IS-DEP", operator="IS-TRUE", right="IS-DEP")
    assert emit_perform_until(until, 0, [], ctx) == [
        'while (!(_cobolEquals(wsType, "D"))) {'
    ]


def test_a_compound_with_one_untranslatable_term_is_skipped_whole() -> None:
    ctx = _cond_ctx(
        _TYPES88,
        _names(BAD=("WS-TYPE", ("ZERO",)), **{"IS-DEP": ("WS-TYPE", ("'D'",))}),
    )
    cond = IRIf(
        left="IS-DEP",
        operator="IS-TRUE",
        right="IS-DEP",
        extra_terms=(
            IRConditionTerm(
                connector="AND", left="BAD", operator="IS-TRUE", right="BAD"
            ),
        ),
    )
    diags: list[Any] = []
    assert emit_if(cond, 0, diags, ctx) == []  # never a header with a term missing
    assert [d.code for d in diags] == ["BE007"]


# ===========================================================================
# 4. build_condition_names: parent + values off the real AST
# ===========================================================================


def _ast(*data_lines: str):
    source = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. T.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        + "".join(f"       {line}\n" for line in data_lines)
        + "       PROCEDURE DIVISION.\n       P1.\n           STOP RUN.\n"
    )
    return ProgramParser().parse(CobolLexer().tokenize(source, filename="s.cbl"))


def test_build_condition_names_resolves_the_parent_and_values() -> None:
    names = build_condition_names(
        _ast(
            "01  REC.",
            "    05  A PIC X(1) VALUE 'D'.",
            "        88  A-DEP VALUE 'D'.",
            "        88  A-KNOWN VALUES 'D' 'W'.",
            "    05  B PIC S9(3) VALUE 0.",
            "        88  B-NEG VALUE -1.",
            "        88  B-HALF VALUES .5 -.5.",
            "01  C PIC X(2) VALUE 'ZZ'.",
            "    88  C-IS VALUE IS 'ZZ'.",
        )
    )
    assert names == {
        "A-DEP": ConditionName("A-DEP", "A", ("'D'",)),
        "A-KNOWN": ConditionName("A-KNOWN", "A", ("'D'", "'W'")),
        "B-NEG": ConditionName("B-NEG", "B", ("-1",)),
        "B-HALF": ConditionName("B-HALF", "B", (".5", "-.5")),
        "C-IS": ConditionName("C-IS", "C", ("'ZZ'",)),
    }


def test_build_condition_names_edge_cases() -> None:
    assert build_condition_names(None) == {}
    assert build_condition_names(_ast("01  A PIC X.")) == {}
    # an entry with no preceding item has no parent, and is omitted
    assert build_condition_names(_ast("    88  ORPHAN VALUE 'X'.")) == {}
    # a condition on a group parent is kept (the group is a String)
    assert set(build_condition_names(_ast("01  G.", "    88  G-ON VALUE 'Y'."))) == {
        "G-ON"
    }


def test_build_condition_context_types_come_from_the_field_list() -> None:
    ctx = build_condition_context(
        [
            JavaField(java_name="wsA", java_type="String"),
            JavaField(java_name="wsN", java_type="int"),
        ],
        _names(C=("WS-A", ("'X'",))),
    )
    assert ctx.field_types == {"wsA": "String", "wsN": "int"}
    assert "C" in ctx.condition_names


# ===========================================================================
# 5. Executed Java against an independent COBOL-semantics oracle
# ===========================================================================

_HARNESS = """\
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class Harness {
    // seed spec:  name=s:TEXT  (a NEW String object)   name=null:   name=i:5   name=d:2.5
    public static void main(String[] args) throws Exception {
        Class<?> c = Class.forName(args[0]);
        Object o = c.getDeclaredConstructor().newInstance();
        for (int k = 1; k < args.length; k++) {
            int eq = args[k].indexOf('=');
            String name = args[k].substring(0, eq);
            String kind = args[k].substring(eq + 1, args[k].indexOf(':', eq));
            String val = args[k].substring(args[k].indexOf(':', eq) + 1);
            Field f = c.getDeclaredField(name);
            f.setAccessible(true);
            switch (kind) {
                case "s": f.set(o, new String(val)); break;
                case "null": f.set(o, null); break;
                case "i": f.setInt(o, Integer.parseInt(val)); break;
                case "d": f.setDouble(o, Double.parseDouble(val)); break;
                default: throw new IllegalArgumentException(kind);
            }
        }
        c.getMethod("run").invoke(o);
        Field[] fs = c.getDeclaredFields();
        Arrays.sort(fs, Comparator.comparing(Field::getName));
        for (Field f : fs) {
            f.setAccessible(true);
            System.out.println(f.getName() + "=" + f.get(o));
        }
    }
}
"""


class _Compiled:
    """One generated class, compiled once, run per seed."""

    def __init__(self, source: str, workdir: Path) -> None:
        result = _analyse(source, workdir)
        assert result.java_source, "no Java generated"
        self.java = result.java_source
        self.result = result
        self._run_dir = workdir / "jrun"
        self._run_dir.mkdir(exist_ok=True)
        self.cls = re.search(r"\bclass\s+(\w+)", self.java).group(1)  # type: ignore[union-attr]
        (self._run_dir / f"{self.cls}.java").write_text(self.java, encoding="utf-8")
        (self._run_dir / "Harness.java").write_text(_HARNESS, encoding="utf-8")
        done = subprocess.run(
            ["javac", "Harness.java", f"{self.cls}.java"],
            cwd=self._run_dir,
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, done.stderr

    def run(self, seeds: dict[str, tuple[str, Any]]) -> dict[str, str]:
        args = [
            f"{name}={kind}:{'' if val is None else val}"
            for name, (kind, val) in seeds.items()
        ]
        proc = subprocess.run(
            ["java", "Harness", self.cls, *args],
            cwd=self._run_dir,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return dict(
            line.split("=", 1) for line in proc.stdout.split("\n") if "=" in line
        )


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "cmp.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _program(data: list[str], proc: list[str]) -> str:
    return (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. CMPSEM.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        + "".join(f"       {line}\n" for line in data)
        + "       PROCEDURE DIVISION.\n       MAIN-PARA.\n"
        + "".join(f"           {line}\n" for line in proc)
        + "           STOP RUN.\n"
    )


# --- independent oracle of the COBOL semantics -----------------------------


def cobol_text_equal(a: str | None, b: str | None) -> bool:
    """COBOL alphanumeric equality: the shorter operand is padded with spaces,
    so trailing spaces never matter; a never-set field is blank."""
    return (a or "").rstrip(" ") == (b or "").rstrip(" ")


def numeric_equal(a: Any, b: Any) -> bool:
    return Decimal(str(a)) == Decimal(str(b))


# ---------------------------------------------------------------------------
# 5a. Text comparisons
# ---------------------------------------------------------------------------

_TEXT_DATA = [
    "01  WS-CODE  PIC X(6) VALUE 'AUTO'.",
    "01  WS-OTHER PIC X(6) VALUE 'AUTO'.",
    "01  WS-N     PIC 9(3) VALUE 5.",
    "01  WS-AMT   PIC 9(3)V99 VALUE 2.50.",
    "01  R01 PIC X(1) VALUE 'N'.",
    "01  R02 PIC X(1) VALUE 'N'.",
    "01  R03 PIC X(1) VALUE 'N'.",
    "01  R04 PIC X(1) VALUE 'N'.",
    "01  R05 PIC X(1) VALUE 'N'.",
    "01  R06 PIC X(1) VALUE 'N'.",
    "01  R07 PIC X(1) VALUE 'N'.",
    "01  R08 PIC X(1) VALUE 'N'.",
    "01  R09 PIC X(1) VALUE 'N'.",
]
_TEXT_PROC = [
    "IF WS-CODE = 'AUTO' MOVE 'Y' TO R01 END-IF",
    "IF WS-CODE = 'LIFE' MOVE 'Y' TO R02 END-IF",
    "IF WS-CODE = WS-OTHER MOVE 'Y' TO R03 END-IF",
    "IF WS-CODE != 'AUTO' MOVE 'Y' TO R04 END-IF",
    "IF WS-CODE != WS-OTHER MOVE 'Y' TO R05 END-IF",
    "IF WS-CODE = 'AUTO  ' MOVE 'Y' TO R06 END-IF",
    "IF WS-N = 5 MOVE 'Y' TO R07 END-IF",
    "IF WS-N != 5 MOVE 'Y' TO R08 END-IF",
    "IF WS-AMT = 2.50 MOVE 'Y' TO R09 END-IF",
]


def _text_oracle(
    code: str | None, other: str | None, n: int, amt: float
) -> dict[str, str]:
    """What the COBOL program leaves in R01..R09."""
    checks = [
        cobol_text_equal(code, "AUTO"),
        cobol_text_equal(code, "LIFE"),
        cobol_text_equal(code, other),
        not cobol_text_equal(code, "AUTO"),
        not cobol_text_equal(code, other),
        cobol_text_equal(code, "AUTO  "),
        n == 5,
        n != 5,
        numeric_equal(amt, "2.50"),
    ]
    return {f"r{i:02d}": ("Y" if hit else "N") for i, hit in enumerate(checks, 1)}


@pytest.fixture(scope="module")
def text_program(tmp_path_factory) -> _Compiled:
    if shutil.which("javac") is None:
        pytest.skip("javac not available")
    return _Compiled(_program(_TEXT_DATA, _TEXT_PROC), tmp_path_factory.mktemp("text"))


_TEXT_SEEDS = [
    pytest.param("AUTO", "AUTO", 5, 2.5, id="equal-strings-in-distinct-objects"),
    pytest.param("LIFE", "LIFE", 5, 2.5, id="different-value-equal-fields"),
    pytest.param("AUTO", "LIFE", 5, 2.5, id="equal-to-literal-unequal-to-field"),
    pytest.param("AUTO  ", "AUTO", 5, 2.5, id="trailing-spaces-are-not-significant"),
    pytest.param("AUTO", "AUTO   ", 5, 2.5, id="padded-other-field"),
    pytest.param("AUTOMO", "AUTO", 5, 2.5, id="longer-string-is-different"),
    pytest.param("auto", "AUTO", 5, 2.5, id="comparison-is-case-sensitive"),
    pytest.param("", "", 5, 2.5, id="empty-strings"),
    pytest.param(None, None, 5, 2.5, id="never-set-fields-are-blank"),
    pytest.param(None, "AUTO", 5, 2.5, id="unset-vs-value"),
    pytest.param("AUTO", "AUTO", 7, 3.0, id="numeric-values-differ"),
]


@needs_java
@pytest.mark.parametrize(("code", "other", "n", "amt"), _TEXT_SEEDS)
def test_text_and_numeric_comparisons_match_cobol(
    text_program, code, other, n, amt
) -> None:
    seeds: dict[str, tuple[str, Any]] = {
        "wsCode": ("null", None) if code is None else ("s", code),
        "wsOther": ("null", None) if other is None else ("s", other),
        "wsN": ("i", n),
        "wsAmt": ("d", amt),
    }
    state = text_program.run(seeds)
    expected = _text_oracle(code, other, n, amt)
    assert {k: state[k] for k in expected} == expected, (seeds, state)


@needs_java
def test_the_default_state_also_matches_cobol(text_program) -> None:
    """Unseeded: the fields hold their compile-time literals (same interned
    object on both sides, which is the one case Java ``==`` happened to get right)."""
    state = text_program.run({})
    assert {k: state[k] for k in _text_oracle("AUTO", "AUTO", 5, 2.5)} == _text_oracle(
        "AUTO", "AUTO", 5, 2.5
    )


def test_generated_text_program_uses_the_helper_and_keeps_numeric_comparisons(
    tmp_path,
) -> None:
    java = _analyse(_program(_TEXT_DATA, _TEXT_PROC), tmp_path).java_source
    assert 'if (_cobolEquals(wsCode, "AUTO")) {' in java
    assert "if (!_cobolEquals(wsCode, wsOther)) {" in java
    assert "if (wsN == 5) {" in java and "if (wsN != 5) {" in java
    assert "if (wsAmt == 2.50) {" in java
    assert not re.search(r'(?:==|!=) "', java)  # no identity comparison left


# ---------------------------------------------------------------------------
# 5b. Level-88 condition-names
# ---------------------------------------------------------------------------

_COND_DATA = [
    "01  WS-TYPE PIC X(1) VALUE 'D'.",
    "    88  IS-DEP VALUE 'D'.",
    "    88  IS-WD VALUE 'W'.",
    "    88  IS-KNOWN VALUES 'D' 'W' 'T'.",
    "01  WS-LVL PIC S9(3) VALUE 0.",
    "    88  IS-NEG VALUE -1.",
    "    88  IS-SMALL VALUES -1 0 +1.",
    "    88  IS-ZERO VALUE ZERO.",
    "01  WS-RATE PIC S9(3)V99 VALUE 0.",
    "    88  IS-HALF VALUE .5.",
    "    88  IS-NEGHALF VALUE IS -.5.",
    "    88  IS-RATES VALUES ARE 0.50 -0.50 2.25.",
    "01  WS-PLAIN PIC X(4) VALUE 'AUTO'.",
    "    88  IS-AUTO-PAD VALUE 'AUTO  '.",
] + [f"01  R{i:02d} PIC X(1) VALUE 'N'." for i in range(1, 16)]

_COND_PROC = [
    "IF IS-DEP MOVE 'Y' TO R01 END-IF",
    "IF IS-WD MOVE 'Y' TO R02 END-IF",
    "IF IS-KNOWN MOVE 'Y' TO R03 END-IF",
    "IF NOT IS-KNOWN MOVE 'Y' TO R04 END-IF",
    "IF IS-NEG MOVE 'Y' TO R05 END-IF",
    "IF IS-SMALL MOVE 'Y' TO R06 END-IF",
    "IF IS-ZERO MOVE 'Y' TO R07 END-IF",
    "IF NOT IS-SMALL MOVE 'Y' TO R08 END-IF",
    "IF IS-HALF MOVE 'Y' TO R09 END-IF",
    "IF IS-NEGHALF MOVE 'Y' TO R10 END-IF",
    "IF IS-RATES MOVE 'Y' TO R11 END-IF",
    "IF IS-AUTO-PAD MOVE 'Y' TO R12 END-IF",
    "IF IS-DEP AND IS-SMALL MOVE 'Y' TO R13 END-IF",
    "IF IS-WD OR IS-NEG MOVE 'Y' TO R14 END-IF",
    "IF NOT IS-DEP AND NOT IS-NEG MOVE 'Y' TO R15 END-IF",
]


def _cond_oracle(
    typ: str | None, lvl: int, rate: float, plain: str | None
) -> dict[str, str]:
    """Independent evaluation of every 88 from the parent's value and the
    declared VALUE list (written out here, not read from the AST)."""
    is_dep = cobol_text_equal(typ, "D")
    is_wd = cobol_text_equal(typ, "W")
    is_known = any(cobol_text_equal(typ, v) for v in ("D", "W", "T"))
    is_neg = numeric_equal(lvl, -1)
    is_small = any(numeric_equal(lvl, v) for v in (-1, 0, 1))
    is_zero = numeric_equal(lvl, 0)
    is_half = numeric_equal(rate, "0.5")
    is_neghalf = numeric_equal(rate, "-0.5")
    is_rates = any(numeric_equal(rate, v) for v in ("0.50", "-0.50", "2.25"))
    is_auto_pad = cobol_text_equal(plain, "AUTO  ")
    checks = [
        is_dep,
        is_wd,
        is_known,
        not is_known,
        is_neg,
        is_small,
        is_zero,
        not is_small,
        is_half,
        is_neghalf,
        is_rates,
        is_auto_pad,
        is_dep and is_small,
        is_wd or is_neg,
        (not is_dep) and (not is_neg),
    ]
    return {f"r{i:02d}": ("Y" if hit else "N") for i, hit in enumerate(checks, 1)}


@pytest.fixture(scope="module")
def cond_program(tmp_path_factory) -> _Compiled:
    if shutil.which("javac") is None:
        pytest.skip("javac not available")
    return _Compiled(_program(_COND_DATA, _COND_PROC), tmp_path_factory.mktemp("cond"))


_COND_SEEDS = [
    pytest.param("D", 0, 0.5, "AUTO", id="dep-zero-half"),
    pytest.param("W", -1, -0.5, "AUTO  ", id="wd-neg-neghalf-padded"),
    pytest.param("T", 1, 2.25, "AUT", id="known-not-dep-small-rate"),
    pytest.param("X", 5, 3.0, "AUTO", id="nothing-holds"),
    pytest.param("d", -1, 0.0, "auto", id="lower-case-is-not-equal"),
    pytest.param("D ", 0, -0.5, "AUTO", id="trailing-space-on-parent"),
    pytest.param(None, 1, 0.5, None, id="never-set-text-parents"),
    pytest.param("W", 5, 2.25, "AUTO", id="wd-only"),
]


@needs_java
@pytest.mark.parametrize(("typ", "lvl", "rate", "plain"), _COND_SEEDS)
def test_condition_names_evaluate_like_cobol_true_and_false(
    cond_program, typ, lvl, rate, plain
) -> None:
    seeds: dict[str, tuple[str, Any]] = {
        "wsType": ("null", None) if typ is None else ("s", typ),
        "wsLvl": ("i", lvl),
        "wsRate": ("d", rate),
        "wsPlain": ("null", None) if plain is None else ("s", plain),
    }
    state = cond_program.run(seeds)
    expected = _cond_oracle(typ, lvl, rate, plain)
    assert {k: state[k] for k in expected} == expected, (seeds, state)


@needs_java
def test_the_default_condition_state_matches_cobol(cond_program) -> None:
    expected = _cond_oracle("D", 0, 0.0, "AUTO")
    state = cond_program.run({})
    assert {k: state[k] for k in expected} == expected


def test_generated_condition_program_has_no_condition_fields_and_no_be007(
    tmp_path,
) -> None:
    result = _analyse(_program(_COND_DATA, _COND_PROC), tmp_path)
    assert not [d for d in result.backend_diagnostics if d.code == "BE007"]
    assert "cannot be translated" not in result.java_source
    for name in ("isDep", "isWd", "isKnown", "isNeg", "isSmall", "isZero", "isHalf"):
        assert f" {name};" not in result.java_source  # Stage 23: no storage field
    assert '_cobolEquals(wsType, "D")' in result.java_source
    assert "wsLvl == -1" in result.java_source  # signed 88 value, Stage 23 parser


# ---------------------------------------------------------------------------
# 5c. PERFORM UNTIL <condition-name> (hand-built IR: the COBOL parser does not
#     yet accept a bare condition-name there, but the backend supports it)
# ---------------------------------------------------------------------------


def _program_ir(*instrs: Any) -> IRProgram:
    block = IRBasicBlock(label="entry", instructions=tuple(instrs))
    fn = IRFunction(name="__entry__", blocks=(block,))
    return IRProgram(name="Loop", modules=(IRModule(name="Loop", functions=(fn,)),))


@needs_java
@pytest.mark.parametrize("flag", ["Y", "N", "Y  ", None])
def test_perform_until_condition_name_executes_like_cobol(tmp_path, flag) -> None:
    program = _program_ir(
        IRPerformUntil(left="IS-DONE", operator="IS-TRUE", right="IS-DONE"),
        IRMove(source="7", result="WS-N"),
        IRMove(source="'Y'", result="WS-FLAG"),
        IREndPerform(),
    )
    fields = [
        JavaField(java_name="wsFlag", java_type="String"),
        JavaField(java_name="wsN", java_type="int"),
    ]
    java = generate_with_diagnostics(
        program, fields, condition_names=_names(**{"IS-DONE": ("WS-FLAG", ("'Y'",))})
    ).source
    assert 'while (!(_cobolEquals(wsFlag, "Y"))) {' in java
    d = tmp_path / "loop"
    d.mkdir()
    (d / "Loop.java").write_text(java, encoding="utf-8")
    (d / "Harness.java").write_text(_HARNESS, encoding="utf-8")
    assert (
        subprocess.run(
            ["javac", "Harness.java", "Loop.java"], cwd=d, capture_output=True
        ).returncode
        == 0
    )
    args = [
        "java",
        "Harness",
        "Loop",
        "wsN=i:0",
        f"wsFlag={'null' if flag is None else 's'}:{flag or ''}",
    ]
    out = subprocess.run(args, cwd=d, capture_output=True, text=True).stdout
    state = dict(line.split("=", 1) for line in out.split("\n") if "=" in line)
    # COBOL: PERFORM UNTIL tests before each pass, so the body runs iff the
    # condition is not already true; the body sets the flag, ending the loop
    done_already = cobol_text_equal(flag, "Y")
    assert state["wsN"] == ("0" if done_already else "7")
    assert cobol_text_equal(state["wsFlag"], "Y")


# ===========================================================================
# 6. Rejected 88 forms stay rejected; unrelated IF behavior is unchanged
# ===========================================================================


def _condition_names_of(*data_lines: str) -> dict[str, ConditionName]:
    return build_condition_names(_ast(*data_lines))


@pytest.mark.parametrize(
    "clause",
    ["VALUE 1 THRU 5", "VALUES 1 THRU 5", "VALUES 1, 2", "VALUE - 1", "VALUE + .5"],
)
def test_unsupported_88_forms_remain_rejected_and_untranslated(
    clause, tmp_path
) -> None:
    source = _program(
        ["01  P PIC S9(3) VALUE 0.", f"    88  BAD {clause}."],
        ["IF BAD MOVE 'X' TO P END-IF"],
    )
    result = _analyse(source, tmp_path)
    assert "SYN005" in [str(d.code) for d in result.syntax_diagnostics]
    assert "BAD" not in _condition_names_of(
        "01  P PIC S9(3) VALUE 0.", f"    88  BAD {clause}."
    )
    assert "_cobolEquals" not in result.java_source  # nothing was guessed


def test_88_with_an_untranslatable_value_is_omitted_with_be007(tmp_path) -> None:
    source = _program(
        ["01  P PIC X(2) VALUE 'AA'.", "    88  ZEROISH VALUE ZERO."],
        ["MOVE 'B' TO P", "IF ZEROISH MOVE 'X' TO P END-IF"],
    )
    result = _analyse(source, tmp_path)
    assert any(d.code == "BE007" for d in result.backend_diagnostics)
    assert "// TODO: IF condition cannot be translated (BE007)" in result.java_source
    assert 'p = "X"' not in result.java_source


def test_ordering_mixed_and_unknown_comparisons_are_unchanged(tmp_path) -> None:
    source = _program(
        [
            "01  WS-CODE PIC X(4) VALUE 'AUTO'.",
            "01  WS-N PIC 9(3) VALUE 0.",
            "01  WS-R PIC X(1).",
        ],
        [
            "IF WS-CODE > 'AUTO' MOVE 'Y' TO WS-R END-IF",
            "IF WS-CODE = 5 MOVE 'Y' TO WS-R END-IF",
            "IF WS-N = 'A' MOVE 'Y' TO WS-R END-IF",
            "IF WS-N > 3 MOVE 'Y' TO WS-R END-IF",
        ],
    )
    java = _analyse(source, tmp_path).java_source
    assert 'if (wsCode > "AUTO") {' in java  # ordering: collating sequence, untouched
    assert "if (wsCode == 5) {" in java  # mixed: untouched
    assert 'if (wsN == "A") {' in java  # mixed: untouched
    assert "if (wsN > 3) {" in java  # numeric: untouched
    assert "_cobolEquals" not in java and "static boolean" not in java  # no helper


# ===========================================================================
# 7. The helper: emitted only when used, and invisible to method scanners
# ===========================================================================


def test_the_helper_is_emitted_only_by_a_class_that_uses_it(tmp_path) -> None:
    plain = _analyse(
        _program(["01  WS-N PIC 9(3) VALUE 0."], ["IF WS-N = 0 MOVE 1 TO WS-N END-IF"]),
        tmp_path,
    ).java_source
    assert COBOL_EQUALS not in plain
    used = _analyse(
        _program(
            ["01  WS-C PIC X(1) VALUE 'A'."], ["IF WS-C = 'A' MOVE 'B' TO WS-C END-IF"]
        ),
        tmp_path,
    ).java_source
    assert used.count(f"static boolean {COBOL_EQUALS}(") == 1
    assert used.count("{") == used.count("}")


def test_the_helper_is_not_mistaken_for_a_cobol_paragraph(tmp_path) -> None:
    """Behavioral extraction, the Java project generator and the chunker read
    ``public``/``private``/``protected`` methods back as paragraphs; the helper is
    package-private, so none of them sees it."""
    from app.behavioral.extraction.extractor import _METHOD_RE as extractor_re
    from app.java_modernization.generation.generator import _METHOD_RE as project_re
    from app.knowledge.chunkers import _JAVA_METHOD_RE as chunker_re

    java = _analyse(
        _program(
            ["01  WS-C PIC X(1) VALUE 'A'."], ["IF WS-C = 'A' MOVE 'B' TO WS-C END-IF"]
        ),
        tmp_path,
    ).java_source
    assert COBOL_EQUALS in java
    for regex in (extractor_re, project_re, chunker_re):
        assert COBOL_EQUALS not in [m.group(1) for m in regex.finditer(java)]


# ===========================================================================
# 8. The real corpus
# ===========================================================================


@pytest.fixture(scope="module")
def policy_redefines():
    return AnalysisService().analyze_file(SOURCES / "policy_redefines.cbl")


def test_real_source_text_comparisons_are_translated(policy_redefines) -> None:
    java = policy_redefines.java_source
    assert 'if (_cobolEquals(policyKind, "AUTO")) {' in java
    assert 'if (_cobolEquals(policyKind, "LIFE")) {' in java
    assert not re.search(r'(?:==|!=) "', java)
    assert java.count(f"static boolean {COBOL_EQUALS}(") == 1
    assert java.count("{") == java.count("}")


@needs_java
def test_real_source_compiles_and_branches_like_cobol(
    policy_redefines, tmp_path
) -> None:
    """``IF POLICY-KIND = 'AUTO'`` ... ``ELSE IF POLICY-KIND = 'LIFE'`` with the
    kind held in a *distinct* String object -- which Java ``==`` got wrong."""
    java = policy_redefines.java_source
    cls = re.search(r"\bclass\s+(\w+)", java).group(1)  # type: ignore[union-attr]
    d = tmp_path / "real"
    d.mkdir()
    (d / f"{cls}.java").write_text(java, encoding="utf-8")
    (d / "Harness.java").write_text(_HARNESS, encoding="utf-8")
    done = subprocess.run(
        ["javac", "Harness.java", f"{cls}.java"], cwd=d, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr

    # the AUTO branch calls the (stub) paragraph method; the ELSE branch of LIFE
    # assigns finalCalculatedPrem = annualBasePrem (1200.0). A kind that is
    # neither takes that final else path; AUTO / LIFE take the stub branches.
    def run(kind: str) -> dict[str, str]:
        out = subprocess.run(
            ["java", "Harness", cls, f"policyKind=s:{kind}"],
            cwd=d,
            capture_output=True,
            text=True,
        ).stdout
        return dict(line.split("=", 1) for line in out.split("\n") if "=" in line)

    assert run("AUTO")["finalCalculatedPrem"] == "0.0"  # AUTO branch: no assignment
    assert run("LIFE")["finalCalculatedPrem"] == "0.0"  # LIFE branch: no assignment
    assert run("AUTO  ")["finalCalculatedPrem"] == "0.0"  # padded: still AUTO
    assert run("BOAT")["finalCalculatedPrem"] == "1200.0"  # neither: else path


def test_real_corpus_only_these_three_sources_use_the_helper(tmp_path) -> None:
    """Across all 45 corpus sources exactly three carry the helper: the ones
    with a text comparison in *reachable* code whose operands are both known
    text (the other text comparisons sit in paragraph bodies the backend
    skips).

    Was only ``t_policy_redefines`` (Stage 24); task #stage25
    (docs/MMIM_NEGATED_COMPARISON_FIX.md) makes ``t_batch_acct_update``'s
    ``IF WS-FILE-STATUS NOT = '00'`` parse for the first time, and it is
    reachable (a separate, pre-existing, unrelated parser gap -- an
    out-of-line ``PERFORM ... UNTIL <paragraph>`` drops the entry
    paragraph's ``GOBACK`` -- happens to make it so). Task #stage27
    (docs/MMIM_FILE_SECTION_FIELDS_FIX.md) adds ``t_daily_trans_report``:
    its ``IF FD-TX-VAL > 10000.00 OR FD-TX-SUSPICIOUS = 'Y'`` was always
    reachable, but ``FD-TX-SUSPICIOUS``'s type was previously unknown (the
    field was never declared at all) -- now that FILE SECTION fields are
    declared like any other, ``ConditionContext`` knows it is a ``String``
    and the comparison correctly gets the helper instead of identity ``==``.
    ``t_inventory_extract`` and ``t_payroll_file_post`` -- the other two
    FILE-SECTION sources -- declare FD fields too but never compare one
    against a text literal, so they do not join this list."""
    from app.dataset.corpus import load_training_corpus

    users = []
    for rec in load_training_corpus():
        path = tmp_path / f"{rec.source_id}.cbl"
        path.write_text(rec.source, encoding="utf-8")
        java = AnalysisService().analyze_file(path).java_source or ""
        if COBOL_EQUALS in java:
            users.append(rec.source_id)
    assert users == [
        "t_batch_acct_update",
        "t_daily_trans_report",
        "t_policy_redefines",
    ]
