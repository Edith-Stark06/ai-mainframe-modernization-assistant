"""
Java translation of ``GO TO`` / ``IRJump`` (Stage 19).

Purpose:
    Stage 17 made real ``GO TO paragraph-name`` reach the IR as ``IRJump``,
    but the Java backend still lowered it to ``// TODO: translate IRJump``
    and let every paragraph fall through -- behaviorally wrong: a program
    that jumps over a paragraph executed it anyway.

    Java has no ``goto`` and the backend's flat model has no paragraphs, so
    when the program contains a translatable jump the body is lowered as a
    paragraph dispatcher (``while``/``switch`` on a paragraph index, jumps as
    labeled ``continue``; see ``_collect_statements``). These tests prove it
    the strong way wherever the program is executable: the generated Java is
    compiled with real ``javac``, *executed*, and every field is compared with
    an independent interpreter of the same IR under COBOL semantics (paragraph
    fall-through + ``GO TO``) -- the oracle never looks at the Java text.

    Every executed case is seeded with identical initial field values on both
    sides. That is deliberate: it makes each test a fair, self-contained test
    of the *jump logic* that does not depend on how ``VALUE`` clauses are
    initialized. (Stage 20 later made ``VALUE`` clauses real Java field
    initializers; ``tests/backend/test_java_value_initializer.py`` runs
    ``t_goto_spaghetti`` unseeded.)

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
from typing import Any

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.generator import generate_with_diagnostics
from app.backend.java.naming import to_java_field_name
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRAdd,
    IRDisplay,
    IRElse,
    IREndIf,
    IRIf,
    IRJump,
    IRMove,
    IRReturn,
)
from app.ir.program import IRFunction, IRModule, IRProgram

SOURCES = Path("data/sources/phase6-v2")

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)

_HARNESS = """\
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class Harness {
    public static void main(String[] args) throws Exception {
        Class<?> c = Class.forName(args[0]);
        Object o = c.getDeclaredConstructor().newInstance();
        for (int i = 1; i < args.length; i++) {
            String[] kv = args[i].split("=", 2);
            Field f = c.getDeclaredField(kv[0]);
            f.setAccessible(true);
            if (f.getType() == int.class) f.setInt(o, Integer.parseInt(kv[1]));
            else f.set(o, kv[1]);
        }
        c.getMethod("run").invoke(o);
        Field[] fs = c.getDeclaredFields();
        Arrays.sort(fs, Comparator.comparing(Field::getName));
        for (Field f : fs) { f.setAccessible(true); System.out.println(f.getName() + "=" + f.get(o)); }
    }
}
"""

# ---------------------------------------------------------------------------
# Independent oracle: executes the IR with COBOL semantics
# ---------------------------------------------------------------------------


def _oracle(
    instructions: list[Any], order: list[str], initial: dict[str, Any]
) -> dict[str, Any]:
    """Run the flat IR under COBOL semantics: paragraphs fall through, GO TO
    transfers control, STOP RUN/GOBACK ends the program. PERFORM (an IRCall)
    is a no-op, mirroring the backend's documented empty-stub behavior."""
    state: dict[str, Any] = dict(initial)
    ins = list(instructions)
    names = [n.upper() for n in order]
    first: dict[str, int] = {}
    for i, x in enumerate(ins):
        p = (x.paragraph or "").upper()
        if p and p not in first:
            first[p] = i

    def entry(target: str) -> int:
        target = target.upper()
        assert target in names, f"oracle: GO TO to unknown paragraph {target}"
        for n in names[names.index(target) :]:
            if n in first:
                return first[n]
        return len(ins)  # empty trailing paragraph: falls off the program

    else_of: dict[int, int] = {}
    end_of: dict[int, int] = {}
    if_of_else: dict[int, int] = {}
    start_of_end: dict[int, int] = {}
    stack: list[int] = []
    for i, x in enumerate(ins):
        kind = type(x).__name__
        if kind in ("IRIf", "IRPerformUntil"):
            stack.append(i)
        elif kind == "IRElse":
            else_of[stack[-1]] = i
            if_of_else[i] = stack[-1]
        elif kind in ("IREndIf", "IREndPerform"):
            j = stack.pop()
            end_of[j] = i
            start_of_end[i] = j

    def val(tok: str) -> Any:
        tok = tok.strip()
        if len(tok) >= 2 and tok[0] in "'\"" and tok[-1] == tok[0]:
            return tok[1:-1]
        try:
            return int(tok)
        except ValueError:
            return state.get(tok.upper(), 0)

    def holds(x: Any) -> bool:
        a, b = val(x.left), val(x.right)
        op = {"=": "==", "<>": "!="}.get(x.operator, x.operator)
        return bool(
            {
                "==": a == b,
                "!=": a != b,
                "<": a < b,
                ">": a > b,
                "<=": a <= b,
                ">=": a >= b,
            }[op]
        )

    pc, steps = 0, 0
    while pc < len(ins):
        steps += 1
        assert steps < 10_000, "oracle: runaway program"
        x = ins[pc]
        kind = type(x).__name__
        if kind == "IRMove":
            state[x.result.upper()] = val(x.source)
        elif kind == "IRAdd":
            state[x.right.upper()] = state.get(x.right.upper(), 0) + val(x.left)
        elif kind == "IRSubtract":
            state[x.right.upper()] = state.get(x.right.upper(), 0) - val(x.left)
        elif kind == "IRIf":
            if not holds(x):
                pc = (else_of[pc] + 1) if pc in else_of else end_of[pc]
                continue
        elif kind == "IRElse":
            pc = end_of[if_of_else[pc]]
            continue
        elif kind == "IRPerformUntil":
            if holds(x):  # exit condition already true
                pc = end_of[pc] + 1
                continue
        elif kind == "IREndPerform":
            pc = start_of_end[pc]
            continue
        elif kind == "IRJump":
            pc = entry(x.target)
            continue
        elif kind == "IRReturn":
            break
        pc += 1
    return state


# ---------------------------------------------------------------------------
# Real pipeline + real javac/java
# ---------------------------------------------------------------------------

_DATA = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. GT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-X   PIC 9(3) VALUE 0.
       01  WS-Y   PIC 9(3) VALUE 0.
       01  WS-Z   PIC 9(3) VALUE 0.
       01  PC     PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
"""
_NAMES = ["WS-X", "WS-Y", "WS-Z", "PC"]


def _analyze(source: str, tmp_path: Path) -> Any:
    path = tmp_path / "gt.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _class_name(java: str) -> str:
    m = re.search(r"\bclass\s+(\w+)", java)
    assert m, java
    return m.group(1)


def _java_run(java: str, tmp_path: Path, initial: dict[str, Any]) -> dict[str, str]:
    d = tmp_path / "jrun"
    d.mkdir(exist_ok=True)
    cls = _class_name(java)
    (d / f"{cls}.java").write_text(java, encoding="utf-8")
    (d / "Harness.java").write_text(_HARNESS, encoding="utf-8")
    comp = subprocess.run(
        ["javac", "Harness.java", f"{cls}.java"], cwd=d, capture_output=True, text=True
    )
    assert comp.returncode == 0, comp.stderr
    args = [f"{to_java_field_name(k)}={v}" for k, v in initial.items()]
    run = subprocess.run(
        ["java", "Harness", cls, *args], cwd=d, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    return dict(line.split("=", 1) for line in run.stdout.splitlines())


def _agree(
    source: str,
    tmp_path: Path,
    initial: dict[str, Any] | None = None,
    names: list[str] | None = None,
) -> tuple[Any, dict[str, str]]:
    """Compile+execute the generated Java and require every named field to equal
    the COBOL-semantics oracle's final value. Returns (analysis, java_state)."""
    initial = initial or {}
    result = _analyze(source, tmp_path)
    assert result.java_source, "no Java generated"
    java_state = _java_run(result.java_source, tmp_path, initial)
    order = [p.name for p in result.ast.procedure_division.paragraphs]
    block = result.ir.modules[0].functions[0].blocks[0]
    expected = _oracle(list(block.instructions), order, initial)
    for name in names or _NAMES:
        want = str(expected.get(name, 0))
        assert java_state[to_java_field_name(name)] == want, (
            name,
            java_state,
            expected,
        )
    return result, java_state


def _src(body: str) -> str:
    return _DATA + body


# ===========================================================================
# The task's semantic example, plus forward / backward
# ===========================================================================


@needs_java
def test_go_to_skips_the_paragraph_between_source_and_target(tmp_path) -> None:
    """A: GO TO C. MOVE 1 TO Z.  B: MOVE 2 TO Y.  C: MOVE 3 TO X.
    B's MOVE must NOT run as fall-through after the GO TO (nor the dead MOVE
    after it in A)."""
    _, state = _agree(
        _src(
            "       A.\n           GO TO C.\n           MOVE 1 TO WS-Z.\n"
            "       B.\n           MOVE 2 TO WS-Y.\n"
            "       C.\n           MOVE 3 TO WS-X.\n"
        ),
        tmp_path,
    )
    assert (state["wsX"], state["wsY"], state["wsZ"]) == ("3", "0", "0")


@needs_java
def test_backward_go_to_loops_until_the_condition_releases_it(tmp_path) -> None:
    _, state = _agree(
        _src(
            "       MAIN.\n           MOVE 0 TO WS-X.\n"
            "       LOOP-PARA.\n           ADD 1 TO WS-X.\n"
            "           IF WS-X < 3\n               GO TO LOOP-PARA\n"
            "           END-IF.\n"
            "       DONE.\n           MOVE 9 TO WS-Y.\n"
        ),
        tmp_path,
    )
    assert (state["wsX"], state["wsY"]) == ("3", "9")


# ===========================================================================
# Jumps inside IF branches (both outcomes of each condition)
# ===========================================================================

_IF_THEN = _src(
    "       A.\n           IF WS-X = 0\n               GO TO C\n           END-IF.\n"
    "       B.\n           MOVE 2 TO WS-Y.\n"
    "       C.\n           MOVE 3 TO WS-Z.\n"
)


@needs_java
@pytest.mark.parametrize("x", [0, 1])
def test_go_to_in_if_then_branch_both_outcomes(tmp_path, x) -> None:
    _, state = _agree(_IF_THEN, tmp_path, {"WS-X": x})
    # taken: B skipped; not taken: B runs (fall-through) then C
    assert state["wsY"] == ("0" if x == 0 else "2")
    assert state["wsZ"] == "3"


_IF_ELSE = _src(
    "       A.\n           IF WS-X = 1\n               MOVE 5 TO WS-Y\n"
    "           ELSE\n               GO TO C\n           END-IF.\n"
    "       B.\n           MOVE 2 TO WS-Y.\n"
    "       C.\n           MOVE 3 TO WS-Z.\n"
)


@needs_java
@pytest.mark.parametrize("x", [0, 1])
def test_go_to_in_if_else_branch_both_outcomes(tmp_path, x) -> None:
    _, state = _agree(_IF_ELSE, tmp_path, {"WS-X": x})
    # ELSE taken (x=0): jump over B -> Y stays 0. THEN taken (x=1): Y=5, then B runs -> Y=2.
    assert state["wsY"] == ("0" if x == 0 else "2")
    assert state["wsZ"] == "3"


@needs_java
@pytest.mark.parametrize("x", [0, 1])
def test_if_whose_branches_both_jump_followed_by_dead_code_still_compiles(
    tmp_path, x
) -> None:
    """javac rejects a statement after an if/else whose branches both cannot
    complete normally ('unreachable statement'). The if(true) idiom avoids it;
    the dead MOVE must never execute."""
    _, state = _agree(
        _src(
            "       A.\n           IF WS-X = 0\n               GO TO B\n"
            "           ELSE\n               GO TO C\n           END-IF.\n"
            "           MOVE 5 TO WS-Z.\n"
            "       B.\n           MOVE 1 TO WS-Y.\n           STOP RUN.\n"
            "       C.\n           MOVE 2 TO WS-Y.\n"
        ),
        tmp_path,
        {"WS-X": x},
    )
    assert state["wsZ"] == "0"
    assert state["wsY"] == ("1" if x == 0 else "2")


# ===========================================================================
# Repeated targets, multi-statement targets, fall-through after the target
# ===========================================================================


@needs_java
def test_repeated_jumps_to_the_same_target_and_multi_statement_target(tmp_path) -> None:
    result, state = _agree(
        _src(
            "       A.\n           IF WS-X = 0\n               GO TO C\n           END-IF.\n"
            "           GO TO C.\n"
            "       B.\n           MOVE 7 TO WS-Y.\n"
            "       C.\n           MOVE 1 TO WS-Z.\n           ADD 4 TO WS-Z.\n"
            "           ADD 5 TO WS-Z.\n"
            "       D.\n           ADD 100 TO WS-X.\n"
        ),
        tmp_path,
    )
    assert (state["wsY"], state["wsZ"], state["wsX"]) == ("0", "10", "100")
    # two jumps, one shared case label for the target
    assert result.java_source.count("_paragraph = 2;") == 2
    assert result.java_source.count("case 2: // C") == 1


@needs_java
def test_stop_run_ends_a_paragraph_but_a_later_paragraph_is_reachable_by_jump(
    tmp_path,
) -> None:
    """A paragraph after STOP RUN is dead in flat Java (skipped, BE011), but
    here it is a GO TO target: the case label must make it reachable again."""
    _, state = _agree(
        _src(
            "       MAIN.\n           GO TO B.\n"
            "       A.\n           MOVE 1 TO WS-X.\n           STOP RUN.\n"
            "       B.\n           MOVE 2 TO WS-X.\n           GO TO A.\n"
        ),
        tmp_path,
    )
    assert state["wsX"] == "1"


@needs_java
def test_go_to_out_of_an_inline_perform_until_loop(tmp_path) -> None:
    """A labeled continue must leave the inline loop, not just continue it."""
    _, state = _agree(
        _src(
            "       MAIN.\n           PERFORM UNTIL WS-X > 100\n"
            "               ADD 1 TO WS-X\n"
            "               IF WS-X = 3\n                   GO TO OUT-PARA\n"
            "               END-IF\n           END-PERFORM.\n"
            "           MOVE 55 TO WS-Y.\n"
            "       OUT-PARA.\n           MOVE 9 TO WS-Z.\n"
        ),
        tmp_path,
    )
    assert (state["wsX"], state["wsY"], state["wsZ"]) == ("3", "0", "9")


@needs_java
def test_a_cobol_item_named_like_the_dispatcher_variable_is_not_shadowed(
    tmp_path,
) -> None:
    """COBOL item PC -> field 'pc'; the dispatcher variable is '_paragraph'
    (an underscore can never appear in a COBOL-derived name), so no shadowing."""
    _, state = _agree(
        _src(
            "       A.\n           MOVE 4 TO PC.\n           GO TO C.\n"
            "       B.\n           MOVE 8 TO PC.\n"
            "       C.\n           ADD 1 TO PC.\n"
        ),
        tmp_path,
    )
    assert state["pc"] == "5"


# ===========================================================================
# Empty/unsupported and missing targets
# ===========================================================================


@needs_java
def test_go_to_an_empty_target_falls_through_to_the_next_paragraph(tmp_path) -> None:
    """E has no representable statements (OPEN is unsupported), so the IR has
    no trace of it; only the threaded paragraph order lets the backend jump to
    it and fall through to F-PARA (skipping B)."""
    result, state = _agree(
        _src(
            "       A.\n           GO TO E.\n"
            "       B.\n           MOVE 1 TO WS-Z.\n"
            "       E.\n           OPEN INPUT SOME-FILE.\n"
            "       F-PARA.\n           MOVE 7 TO WS-Y.\n"
        ),
        tmp_path,
    )
    assert (state["wsY"], state["wsZ"]) == ("7", "0")
    assert "case 2: // E" in result.java_source  # an empty paragraph still has a label


@needs_java
def test_go_to_a_trailing_empty_paragraph_ends_the_program(tmp_path) -> None:
    _, state = _agree(
        _src(
            "       A.\n           GO TO Z-END.\n"
            "       B.\n           MOVE 1 TO WS-Z.\n"
            "       Z-END.\n           OPEN INPUT SOME-FILE.\n"
        ),
        tmp_path,
    )
    assert state["wsZ"] == "0"


# ---------------------------------------------------------------------------
# Hand-built IR (no javac): fallback rules
# ---------------------------------------------------------------------------


def _program(*instrs: Any) -> IRProgram:
    block = IRBasicBlock(label="entry", instructions=tuple(instrs))
    fn = IRFunction(name="__entry__", blocks=(block,))
    return IRProgram(name="T", modules=(IRModule(name="T", functions=(fn,)),))


def test_a_program_with_no_go_to_is_lowered_flat_and_unchanged() -> None:
    java = generate_with_diagnostics(
        _program(
            IRMove(source="1", result="X", paragraph="A"),
            IRMove(source="2", result="Y", paragraph="B"),
        )
    ).source
    assert "_dispatch" not in java and "_paragraph" not in java
    assert "x = 1;" in java and "y = 2;" in java


def test_hand_built_jump_becomes_a_dispatcher_jump() -> None:
    res = generate_with_diagnostics(
        _program(
            IRJump(target="B", paragraph="A"),
            IRMove(source="1", result="Y", paragraph="A"),
            IRMove(source="2", result="X", paragraph="B"),
        )
    )
    assert "case 0: // A" in res.source and "case 1: // B" in res.source
    assert "if (true) { _paragraph = 1; continue _dispatch; } // GO TO B" in res.source
    assert "translate IRJump" not in res.source
    assert res.diagnostics == []


def test_only_an_unresolvable_jump_keeps_todays_flat_todo() -> None:
    """No translatable jump anywhere => byte-for-byte the pre-Stage-19 output
    (still a TODO + BE005), never a dispatcher around nothing."""
    res = generate_with_diagnostics(_program(IRJump(target="NOWHERE", paragraph="A")))
    assert "// TODO: translate IRJump" in res.source
    assert "_dispatch" not in res.source
    assert [d.code for d in res.diagnostics] == ["BE005"]


def test_missing_target_beside_a_resolvable_jump_is_a_todo_with_be012() -> None:
    res = generate_with_diagnostics(
        _program(
            IRJump(target="B", paragraph="A"),
            IRJump(target="NOWHERE", paragraph="B"),
        )
    )
    assert "_paragraph = 1; continue _dispatch;" in res.source
    assert "// TODO: GO TO 'NOWHERE' cannot be translated (BE012)" in res.source
    assert [d.code for d in res.diagnostics] == ["BE012"]
    assert "_paragraph = " not in res.source.split("NOWHERE")[0].split("case 1")[1]


def test_paragraph_order_lets_a_jump_reach_an_empty_paragraph_only_when_given() -> None:
    prog = _program(
        IRJump(target="EMPTY", paragraph="A"),
        IRMove(source="1", result="X", paragraph="B"),
    )
    # without the paragraph list EMPTY is unknown => flat + TODO (unchanged)
    flat = generate_with_diagnostics(prog)
    assert "// TODO: translate IRJump" in flat.source and "_dispatch" not in flat.source
    # with it, EMPTY is a real (label-only) case between A and B
    disp = generate_with_diagnostics(prog, paragraph_order=["A", "EMPTY", "B"])
    assert "_paragraph = 1; continue _dispatch;" in disp.source
    assert "case 1: // EMPTY" in disp.source and "case 2: // B" in disp.source


def test_a_paragraph_order_that_omits_an_ir_paragraph_is_ignored() -> None:
    res = generate_with_diagnostics(
        _program(
            IRJump(target="B", paragraph="A"),
            IRMove(source="1", result="X", paragraph="B"),
        ),
        paragraph_order=["A"],  # does not cover B -> fall back to IR order
    )
    assert "case 0: // A" in res.source and "case 1: // B" in res.source


def test_return_marks_only_its_own_case_dead() -> None:
    res = generate_with_diagnostics(
        _program(
            IRReturn(paragraph="A"),
            IRMove(source="1", result="X", paragraph="A"),  # dead: same case
            IRJump(target="A", paragraph="B"),  # reachable: new case
        )
    )
    assert "x = 1;" not in res.source
    assert "_paragraph = 0; continue _dispatch;" in res.source
    assert [d.code for d in res.diagnostics] == ["BE011"]


def test_jump_inside_nested_if_else_keeps_braces_balanced() -> None:
    java = generate_with_diagnostics(
        _program(
            IRIf(left="X", operator="=", right="1", paragraph="A"),
            IRJump(target="B", paragraph="A"),
            IRElse(paragraph="A"),
            IRDisplay(operand='"E"', paragraph="A"),
            IREndIf(paragraph="A"),
            IRAdd(left="1", right="X", result="X", paragraph="B"),
        )
    ).source
    assert java.count("{") == java.count("}")


# ===========================================================================
# PERFORM behavior is untouched
# ===========================================================================


@needs_java
def test_perform_without_go_to_is_unchanged(tmp_path) -> None:
    result = _analyze(
        _src(
            "       MAIN.\n           PERFORM SUB1.\n           STOP RUN.\n"
            "       SUB1.\n           MOVE 1 TO WS-X.\n"
        ),
        tmp_path,
    )
    java = result.java_source
    assert "_dispatch" not in java
    assert "sub1();" in java and "private void sub1()" in java  # stub call, as before


@needs_java
def test_perform_beside_a_go_to_keeps_its_stub_call(tmp_path) -> None:
    result = _analyze(
        _src(
            "       MAIN.\n           PERFORM SUB1.\n           GO TO DONE.\n"
            "       SUB1.\n           MOVE 1 TO WS-X.\n"
            "       DONE.\n           MOVE 2 TO WS-Y.\n"
        ),
        tmp_path,
    )
    java = result.java_source
    assert "sub1();" in java and "private void sub1()" in java
    assert "_paragraph = 2; continue _dispatch;" in java


# ===========================================================================
# The real corpus program
# ===========================================================================

_SPAGHETTI_INITIAL = {
    "STEP-INDEX": 1,
    "ACCUMULATOR": 0,
    "TERMINAL-STATE": "INITIAL",
    "RETRY-COUNTER": 0,
}


@pytest.fixture(scope="module")
def goto_spaghetti() -> Any:
    return AnalysisService().analyze_file(SOURCES / "goto_spaghetti.cbl")


def test_real_goto_spaghetti_has_no_untranslated_jump(goto_spaghetti) -> None:
    java = goto_spaghetti.java_source
    assert "translate IRJump" not in java
    assert java.count("continue _dispatch;") == 7  # one per real GO TO
    assert java.count("{") == java.count("}")
    assert not [d for d in goto_spaghetti.backend_diagnostics if d.code == "BE012"]


@needs_java
@pytest.mark.parametrize(
    "step_index",
    [1, 0, 2],
    ids=["cobol-VALUE-01:loop-path", "java-default-0:else-path", "other:else-path"],
)
def test_real_goto_spaghetti_executes_like_the_cobol_program(
    goto_spaghetti, tmp_path, step_index
) -> None:
    """Runs the *generated Java* and the IR oracle from the same initial state.
    step_index=1 is the program's real VALUE and drives the interesting path:
    2000 -> 4000 -> 2000 -> 4000 -> 2000 -> 5000 (a backward jump, three
    passes)."""
    initial = dict(_SPAGHETTI_INITIAL, **{"STEP-INDEX": step_index})
    java_state = _java_run(goto_spaghetti.java_source, tmp_path, initial)
    order = [p.name for p in goto_spaghetti.ast.procedure_division.paragraphs]
    block = goto_spaghetti.ir.modules[0].functions[0].blocks[0]
    expected = _oracle(list(block.instructions), order, initial)
    for cobol_name in _SPAGHETTI_INITIAL:
        assert java_state[to_java_field_name(cobol_name)] == str(expected[cobol_name])
    if step_index == 1:
        assert expected["ACCUMULATOR"] == 30 and expected["RETRY-COUNTER"] == 2
        assert expected["STEP-INDEX"] == 4 and expected["TERMINAL-STATE"] == "COMPLETED"
    else:
        assert expected["ACCUMULATOR"] == 50  # 1000 -> ELSE -> 3000 -> 5000
