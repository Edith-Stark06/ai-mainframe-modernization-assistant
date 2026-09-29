"""
Multi-operand ``DISPLAY`` (``DISPLAY 'TOTAL: ' WS-TOTAL``).

Purpose:
    The parser used to join every operand of a ``DISPLAY`` into a single
    string, so ``DISPLAY 'SYSTEM STATUS: ' WS-STATUS`` reached the Java
    backend as one bogus identifier (``systemstatuswsStatus``) and the
    generated program did not compile. The statement now also carries each
    operand separately (``operands``) and the backend concatenates them.

Coverage:
    Parser         -- operand splitting, single-operand shape unchanged,
                      ``UPON`` / ``WITH`` statements left as they were.
    IR             -- ``operands`` propagated; ``display_operands`` uniform.
    Emitter        -- concatenation, ``"" +`` guard for a numeric first
                      operand, PICTURE formatting per operand, subscripted
                      operand skipped with ``BE015``.
    Semantic       -- every operand is checked, so an undefined name in the
                      second position is reported (``SEM003``).
    End to end     -- the generated Java for a real program compiles with
                      ``javac`` and prints the expected line.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.condition_context import build_condition_context
from app.backend.java.field_model import JavaField
from app.backend.java.statement_emitter import emit_display
from app.backend.java.generator import BackendDiagnostic
from app.ir.instructions import IRDisplay
from app.parser.ast.statements import DisplayStatementNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MULTIDISP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A PIC X(5) VALUE 'HELLO'.
       01  WS-B PIC 9(3) VALUE 7.
       01  WS-TABLE.
           05  WS-ITEM PIC X(2) OCCURS 3 TIMES.
"""


def _program(stmt: str) -> str:
    return (
        _HEAD
        + f"       PROCEDURE DIVISION.\n       MAIN-PARA.\n           {stmt}\n           STOP RUN.\n"
    )


def _display(stmt: str) -> DisplayStatementNode:
    program = ProgramParser().parse(
        CobolLexer().tokenize(_program(stmt), filename="d.cbl")
    )
    (node,) = [
        s
        for s in program.procedure_division.paragraphs[0].statements
        if isinstance(s, DisplayStatementNode)
    ]
    return node


def _analyse(stmt: str, tmp_path: Path):
    path = tmp_path / "multidisp.cbl"
    path.write_text(_program(stmt), encoding="utf-8")
    return AnalysisService().analyze_file(path)


# ===========================================================================
# Parser
# ===========================================================================


def test_two_operands_are_split() -> None:
    node = _display("DISPLAY 'TOTAL: ' WS-A.")
    assert node.operands == ("'TOTAL: '", "WS-A")
    assert node.operand == "'TOTAL: ' WS-A"  # joined text is unchanged


def test_three_operands_are_split() -> None:
    node = _display("DISPLAY 'A ' WS-A ' Z'.")
    assert node.operands == ("'A '", "WS-A", "' Z'")


def test_single_operand_keeps_the_old_shape() -> None:
    node = _display("DISPLAY WS-A.")
    assert node.operand == "WS-A"
    assert node.operands == ()
    assert node.display_operands == ("WS-A",)


def test_single_subscripted_operand_keeps_its_structured_form() -> None:
    node = _display("DISPLAY WS-ITEM(2).")
    assert node.operands == ()
    assert node.operand_subscript  # still the structural subscript


def test_subscript_stays_attached_to_its_name_in_a_list() -> None:
    node = _display("DISPLAY 'X ' WS-ITEM(2).")
    assert node.operands == ("'X '", "WS-ITEM ( 2 )")


@pytest.mark.parametrize(
    "stmt",
    ["DISPLAY 'X' WS-A UPON CONSOLE.", "DISPLAY 'X' WS-A WITH NO ADVANCING."],
)
def test_upon_and_with_clauses_are_not_split(stmt: str) -> None:
    node = _display(stmt)
    assert node.operands == ()


# ===========================================================================
# Emitter
# ===========================================================================


def _ctx():
    return build_condition_context(
        [
            JavaField(java_name="wsA", java_type="String", length=5),
            JavaField(
                java_name="wsB",
                java_type="int",
                digits=3,
                decimal_places=0,
                signed=False,
            ),
        ]
    )


def test_emitter_concatenates_literal_and_field() -> None:
    ir = IRDisplay(operand="'X: ' WS-A", operands=("'X: '", "WS-A"))
    out = emit_display(ir, [], _ctx())
    assert out == ['System.out.println("X: " + String.format("%-5s", wsA));']


def test_emitter_formats_each_operand_by_its_picture() -> None:
    ir = IRDisplay(operand="'N: ' WS-B", operands=("'N: '", "WS-B"))
    out = emit_display(ir, [], _ctx())
    assert out == ['System.out.println("N: " + String.format("%03d", wsB));']


def test_emitter_forces_string_concatenation_when_first_operand_is_numeric() -> None:
    ir = IRDisplay(operand="WS-B WS-B", operands=("WS-B", "WS-B"))
    (line,) = emit_display(ir, [], _ctx())
    # Without the leading "" Java would ADD the two numbers.
    assert line.startswith('System.out.println("" + ')


def test_emitter_skips_subscripted_operand_with_a_warning() -> None:
    diagnostics: list[BackendDiagnostic] = []
    ir = IRDisplay(operand="'X' WS-ITEM ( 2 )", operands=("'X'", "WS-ITEM ( 2 )"))
    assert emit_display(ir, diagnostics, _ctx()) == []
    assert [d.code for d in diagnostics] == ["BE015"]


def test_emitter_single_operand_is_unchanged() -> None:
    out = emit_display(IRDisplay(operand="WS-A"), [], _ctx())
    assert out == ['System.out.println(String.format("%-5s", wsA));']


# ===========================================================================
# IR + semantic
# ===========================================================================


def test_ir_carries_the_operands(tmp_path: Path) -> None:
    result = _analyse("DISPLAY 'X: ' WS-A.", tmp_path)
    displays = [
        i
        for module in result.ir.modules
        for fn in module.functions
        for block in fn.blocks
        for i in block.instructions
        if isinstance(i, IRDisplay)
    ]
    assert [d.operands for d in displays] == [("'X: '", "WS-A")]


def test_undefined_name_in_second_position_is_reported(tmp_path: Path) -> None:
    result = _analyse("DISPLAY 'X: ' NO-SUCH-FIELD.", tmp_path)
    codes = [str(getattr(d, "code", "")) for d in result.semantic_diagnostics]
    assert "SEM003" in codes


def test_defined_names_produce_no_semantic_errors(tmp_path: Path) -> None:
    result = _analyse("DISPLAY 'X: ' WS-A ' ' WS-B.", tmp_path)
    codes = [str(getattr(d, "code", "")) for d in result.semantic_diagnostics]
    assert "SEM003" not in codes


# ===========================================================================
# End to end: the generated Java compiles and prints the right line
# ===========================================================================


@pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="JDK not available",
)
def test_generated_java_compiles_and_prints_the_line(tmp_path: Path) -> None:
    result = _analyse("DISPLAY 'STATUS: ' WS-A ' #' WS-B.", tmp_path)
    java = result.java_source
    assert "System.out.println" in java
    name = re.search(r"public\s+(?:final\s+)?class\s+(\w+)", java).group(1)
    (tmp_path / f"{name}.java").write_text(java, encoding="utf-8")
    compiled = subprocess.run(
        ["javac", f"{name}.java"], cwd=tmp_path, capture_output=True, text=True
    )
    assert compiled.returncode == 0, compiled.stderr
    ran = subprocess.run(
        ["java", "-cp", str(tmp_path), name],
        capture_output=True,
        text=True,
    )
    assert "STATUS: HELLO #007" in ran.stdout, ran.stdout + ran.stderr
