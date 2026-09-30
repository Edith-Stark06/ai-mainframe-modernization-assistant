"""
``ACCEPT identifier`` (console input).

Purpose:
    ``ACCEPT`` used to be reported as an unsupported statement (task #108), so
    any program that read input lost those statements from the AST, IR, and
    generated Java. A plain ``ACCEPT identifier`` is now parsed, lowered, and
    translated to a console read typed by the target's declared PICTURE.

Coverage:
    Parser         -- plain ACCEPT parsed; ``FROM DATE`` / ``FROM TIME`` /
                      subscripted target / ``ON EXCEPTION`` still SYN100;
                      following statements survive.
    Semantic       -- an undefined target is reported (``SEM003``).
    Emitter        -- String / int / double helpers; unknown type -> ``BE016``;
                      empty target -> ``BE004``; helper emitted only when used.
    End to end     -- generated Java compiles with ``javac`` and, run with
                      piped stdin, stores what it was given.
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
from app.backend.java.generator import BackendDiagnostic
from app.backend.java.statement_emitter import emit_accept, emit_statement
from app.ir.instructions import IRAccept
from app.parser.ast.statements import AcceptStatementNode, StopRunStatementNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCEPTT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-NAME PIC X(8).
       01  WS-QTY  PIC 9(3).
       01  WS-AMT  PIC 9(3)V99.
       01  WS-TABLE.
           05  WS-ITEM PIC X(2) OCCURS 3 TIMES.
"""


def _program(body: str) -> str:
    return _HEAD + "       PROCEDURE DIVISION.\n       MAIN-PARA.\n" + body


def _parse(body: str):
    program = ProgramParser().parse(
        CobolLexer().tokenize(_program(body), filename="a.cbl")
    )
    return program.procedure_division.paragraphs[0].statements


def _analyse(body: str, tmp_path: Path):
    path = tmp_path / "acceptt.cbl"
    path.write_text(_program(body), encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _ctx():
    return build_condition_context(
        [
            JavaField(java_name="wsName", java_type="String", length=8),
            JavaField(java_name="wsQty", java_type="int", digits=3),
            JavaField(java_name="wsAmt", java_type="double", digits=5),
            JavaField(java_name="wsFlag", java_type="boolean"),
        ]
    )


# ===========================================================================
# Parser
# ===========================================================================


def test_plain_accept_is_parsed() -> None:
    stmts = _parse("           ACCEPT WS-NAME.\n           STOP RUN.\n")
    assert [type(s) for s in stmts] == [AcceptStatementNode, StopRunStatementNode]
    assert stmts[0].target == "WS-NAME"


def test_accept_without_period_before_next_statement() -> None:
    stmts = _parse("           ACCEPT WS-NAME\n           STOP RUN.\n")
    assert [type(s) for s in stmts] == [AcceptStatementNode, StopRunStatementNode]


@pytest.mark.parametrize(
    "stmt",
    [
        "ACCEPT WS-NAME FROM DATE.",
        "ACCEPT WS-NAME FROM TIME.",
        "ACCEPT WS-NAME FROM DAY-OF-WEEK.",
        "ACCEPT WS-ITEM(2).",
        "ACCEPT WS-NAME ON EXCEPTION DISPLAY 'X'.",
    ],
)
def test_unmodelled_accept_forms_stay_unsupported(stmt: str, tmp_path: Path) -> None:
    result = _analyse(f"           {stmt}\n           STOP RUN.\n", tmp_path)
    codes = [getattr(d, "code", "") for d in result.syntax_diagnostics]
    assert "SYN100" in codes
    stmts = _parse(f"           {stmt}\n           STOP RUN.\n")
    assert not any(isinstance(s, AcceptStatementNode) for s in stmts)
    assert any(isinstance(s, StopRunStatementNode) for s in stmts)


# ===========================================================================
# Semantic
# ===========================================================================


def test_undefined_target_is_reported(tmp_path: Path) -> None:
    result = _analyse(
        "           ACCEPT NO-SUCH-FIELD.\n           STOP RUN.\n", tmp_path
    )
    codes = [str(getattr(d, "code", "")) for d in result.semantic_diagnostics]
    assert "SEM003" in codes


def test_defined_target_is_clean(tmp_path: Path) -> None:
    result = _analyse("           ACCEPT WS-NAME.\n           STOP RUN.\n", tmp_path)
    codes = [str(getattr(d, "code", "")) for d in result.semantic_diagnostics]
    assert "SEM003" not in codes


# ===========================================================================
# Emitter
# ===========================================================================


@pytest.mark.parametrize(
    ("cobol", "expected"),
    [
        ("WS-NAME", "wsName = _cobolAcceptLine();"),
        ("WS-QTY", "wsQty = _cobolAcceptInt();"),
        ("WS-AMT", "wsAmt = _cobolAcceptDouble();"),
    ],
)
def test_helper_is_chosen_by_declared_java_type(cobol: str, expected: str) -> None:
    diagnostics: list[BackendDiagnostic] = []
    assert emit_accept(IRAccept(result=cobol), diagnostics, _ctx()) == [expected]
    assert diagnostics == []


def test_dispatcher_routes_accept() -> None:
    out = emit_statement(IRAccept(result="WS-QTY"), [], context=_ctx())
    assert out == ["wsQty = _cobolAcceptInt();"]


def test_unmapped_type_is_skipped_with_be016() -> None:
    diagnostics: list[BackendDiagnostic] = []
    assert emit_accept(IRAccept(result="WS-FLAG"), diagnostics, _ctx()) == []
    assert [d.code for d in diagnostics] == ["BE016"]


def test_missing_context_is_skipped_with_be016() -> None:
    diagnostics: list[BackendDiagnostic] = []
    assert emit_accept(IRAccept(result="WS-NAME"), diagnostics) == []
    assert [d.code for d in diagnostics] == ["BE016"]


def test_empty_target_is_skipped_with_be004() -> None:
    diagnostics: list[BackendDiagnostic] = []
    assert emit_accept(IRAccept(result=""), diagnostics, _ctx()) == []
    assert [d.code for d in diagnostics] == ["BE004"]


def test_helper_is_only_emitted_by_a_class_that_accepts(tmp_path: Path) -> None:
    with_accept = _analyse(
        "           ACCEPT WS-NAME.\n           STOP RUN.\n", tmp_path
    )
    without = _analyse(
        "           MOVE 'A' TO WS-NAME.\n           STOP RUN.\n", tmp_path
    )
    assert "_cobolAcceptLine()" in with_accept.java_source
    assert "static String _cobolAcceptLine" in with_accept.java_source
    assert "_cobolAccept" not in without.java_source


# ===========================================================================
# End to end: compile and run with piped stdin
# ===========================================================================


@pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="JDK not available",
)
def test_generated_java_reads_console_input(tmp_path: Path) -> None:
    body = (
        "           ACCEPT WS-NAME.\n"
        "           ACCEPT WS-QTY.\n"
        "           ACCEPT WS-AMT.\n"
        "           DISPLAY 'NAME=' WS-NAME.\n"
        "           DISPLAY 'QTY=' WS-QTY.\n"
        "           DISPLAY 'AMT=' WS-AMT.\n"
        "           STOP RUN.\n"
    )
    result = _analyse(body, tmp_path)
    java = result.java_source
    match = re.search(r"public\s+(?:final\s+)?class\s+(\w+)", java)
    assert match is not None
    name = match.group(1)
    (tmp_path / f"{name}.java").write_text(java, encoding="utf-8")

    compiled = subprocess.run(
        ["javac", f"{name}.java"], cwd=tmp_path, capture_output=True, text=True
    )
    assert compiled.returncode == 0, compiled.stderr

    ran = subprocess.run(
        ["java", "-cp", str(tmp_path), name],
        input="ALICE\n7\n12.5\n",
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert "NAME=ALICE" in ran.stdout
    assert "QTY=007" in ran.stdout
    assert "AMT=01250" in ran.stdout, ran.stdout


@pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="JDK not available",
)
def test_end_of_input_and_bad_numbers_do_not_crash(tmp_path: Path) -> None:
    body = (
        "           ACCEPT WS-QTY.\n"
        "           ACCEPT WS-NAME.\n"
        "           DISPLAY 'QTY=' WS-QTY.\n"
        "           STOP RUN.\n"
    )
    result = _analyse(body, tmp_path)
    java = result.java_source
    match = re.search(r"public\s+(?:final\s+)?class\s+(\w+)", java)
    assert match is not None
    name = match.group(1)
    (tmp_path / f"{name}.java").write_text(java, encoding="utf-8")
    assert (
        subprocess.run(
            ["javac", f"{name}.java"], cwd=tmp_path, capture_output=True
        ).returncode
        == 0
    )
    ran = subprocess.run(
        ["java", "-cp", str(tmp_path), name],
        input="not-a-number\n",  # then end of input for the second ACCEPT
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert "QTY=000" in ran.stdout
