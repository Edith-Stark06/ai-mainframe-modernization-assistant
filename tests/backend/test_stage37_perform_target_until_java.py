"""
Java backend tests for task #stage37 — out-of-line ``PERFORM
paragraph-name UNTIL condition``.

Purpose:
    ``PerformTargetUntilStatementNode`` lowers to
    ``IRPerformUntil``/``IRCall(comment="PERFORM")``/``IREndPerform`` --
    an IR shape :mod:`app.backend.java.generator` already knew how to
    render before this stage existed: ``_emit_instruction_list`` already
    translates ``IRPerformUntil``/``IREndPerform`` into a Java
    ``while (!(cond)) { ... }`` block (Stage 34), and
    ``_local_perform_targets``/``_collect_outlined_statements`` already
    outline any ``IRCall`` tagged ``comment="PERFORM"`` whose target
    resolves to a local paragraph into a real ``private void`` method
    (Stage 36) -- regardless of whether that call sits at the top level
    or, as here, as the loop's own body. No change to
    ``app/backend/java/generator.py``,
    ``app/backend/java/control_flow_emitter.py``, or
    ``app/backend/java/statement_emitter.py`` was needed for this stage;
    these tests exist to prove that composition actually holds, not to
    exercise new backend code.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analysis.service import AnalysisService

_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-EOF PIC X(1) VALUE SPACE.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(header + "PROCEDURE DIVISION.\n" + body, encoding="utf-8")
    return AnalysisService().analyze_file(path)


_BODY = (
    "MAIN-PARA.\n"
    "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
    "    DISPLAY 'DONE'.\n"
    "    GOBACK.\n"
    "2000-PROCESS-RECORDS.\n"
    "    DISPLAY 'X'.\n"
    "    MOVE 'Y' TO WS-EOF.\n"
)


class TestRealTargetOutlinedNotStubbed:
    def test_no_diagnostics(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        assert not result.backend_diagnostics

    def test_target_is_a_real_method_not_a_be009_stub(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        java = result.java_source
        assert "private void f2000ProcessRecords()" in java
        assert "TODO" not in java
        assert "BE009" not in str(result.backend_diagnostics)

    def test_loop_calls_the_outlined_method(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        run_method = result.java_source.split("public void run()")[1].split(
            "private void"
        )[0]
        assert "while (!(_cobolEquals(wsEof" in run_method
        assert "f2000ProcessRecords();" in run_method

    def test_condition_rendered_correctly(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        assert 'while (!(_cobolEquals(wsEof, "Y"))) {' in result.java_source

    def test_target_body_is_not_duplicated_into_the_loop(self, tmp_path: Path) -> None:
        """The outlined method's own body must appear exactly once --
        never also inlined between the while-loop's braces."""
        result = _analyze(tmp_path, _BODY)
        java = result.java_source
        assert java.count('System.out.println("X")') == 1

    def test_statement_after_loop_is_preserved(self, tmp_path: Path) -> None:
        """The exact defect this stage fixes: DONE/GOBACK after the
        malformed PERFORM used to be silently dropped."""
        result = _analyze(tmp_path, _BODY)
        run_method = result.java_source.split("public void run()")[1].split(
            "private void"
        )[0]
        assert 'System.out.println("DONE")' in run_method
        assert "return;" in run_method


class TestRegressionOtherPerformForms:
    def test_plain_perform_outlining_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA.\n"
            "    STOP RUN.\n"
            "SUB-PARA.\n"
            "    DISPLAY 'X'.\n",
        )
        assert not result.backend_diagnostics
        assert "private void subPara()" in result.java_source

    def test_perform_thru_outlining_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA THRU SUB-PARA-2.\n"
            "    STOP RUN.\n"
            "SUB-PARA.\n"
            "    DISPLAY 'X'.\n"
            "SUB-PARA-2.\n"
            "    DISPLAY 'Y'.\n",
        )
        assert not result.backend_diagnostics
        assert "private void subPara()" in result.java_source

    def test_inline_perform_until_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM UNTIL WS-EOF = 'Y'\n"
            "        DISPLAY 'X'\n"
            "        MOVE 'Y' TO WS-EOF\n"
            "    END-PERFORM.\n"
            "    GOBACK.\n",
        )
        assert not result.backend_diagnostics
        assert 'while (!(_cobolEquals(wsEof, "Y"))) {' in result.java_source
        assert "private void" not in result.java_source  # no paragraph to outline

    def test_perform_varying_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM VARYING WS-A FROM 1 BY 1 UNTIL WS-A > 3\n"
            "        DISPLAY WS-A\n"
            "    END-PERFORM.\n"
            "    GOBACK.\n",
            header=_HEADER + "01 WS-A PIC 9(2) VALUE 0.\n",
        )
        assert not result.backend_diagnostics
        # PERFORM VARYING renders as a Java `for` loop, not `while` --
        # unaffected by this stage either way.
        assert "for (wsA = 1; wsA <= 3; wsA += 1) {" in result.java_source

    def test_call_target_not_local_still_stubbed(self, tmp_path: Path) -> None:
        """An UNTIL-target that resolves to no local paragraph (an
        external sub-program name, or a typo) must keep the ordinary
        BE009 stub path -- this stage only outlines a genuinely local
        target, exactly like plain PERFORM already only does."""
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM NOT-A-REAL-PARAGRAPH UNTIL WS-EOF = 'Y'.\n"
            "    GOBACK.\n",
        )
        assert "BE009" in str(result.backend_diagnostics)
        assert "private void notARealParagraph" in result.java_source


class TestRuntimeExecution:
    """javac success alone does not prove the loop actually iterates the
    right number of times and then falls through -- this actually runs
    the generated program."""

    def test_loop_iterates_and_caller_continues_afterward(self, tmp_path: Path) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE3.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-EOF PIC X(1) VALUE 'N'.\n"
            "01 WS-COUNT PIC 9(3) VALUE 0.\n"
        )
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM 2000-READ-RECORD UNTIL WS-EOF = 'Y'.\n"
            "    DISPLAY WS-COUNT.\n"
            "    GOBACK.\n"
            "2000-READ-RECORD.\n"
            "    ADD 1 TO WS-COUNT.\n"
            "    IF WS-COUNT = 5\n"
            "        MOVE 'Y' TO WS-EOF\n"
            "    END-IF.\n",
            header,
        )
        assert not result.backend_diagnostics
        java_file = tmp_path / "Texe3.java"
        java_file.write_text(result.java_source, encoding="utf-8")

        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe3"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        # Test-after-body semantics: the target runs once per iteration,
        # re-testing WS-EOF after each execution, exiting once it flips
        # to 'Y' on the 5th call -- exactly 5 iterations, not 4 or 6 --
        # and the caller's own DISPLAY after the loop still executes.
        assert run.stdout.strip() == "005"

    def test_condition_already_true_never_performs_target(self, tmp_path: Path) -> None:
        """Standard COBOL ``PERFORM ... UNTIL`` (out-of-line or inline)
        defaults to test-*before* semantics: the condition is checked
        first, and if it is already true, the target is never executed
        -- not even once. This construct's lowering
        (``IRPerformUntil`` -> Java ``while (!(cond)) { target(); }``,
        the identical translation Stage 34's inline form already uses)
        checks the condition before every iteration including the
        first, which is exactly this. Verified directly, rather than
        assumed, by starting WS-EOF already at 'Y' and confirming
        WS-COUNT is never incremented."""
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE4.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-EOF PIC X(1) VALUE 'Y'.\n"
            "01 WS-COUNT PIC 9(3) VALUE 0.\n"
        )
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM 2000-READ-RECORD UNTIL WS-EOF = 'Y'.\n"
            "    DISPLAY WS-COUNT.\n"
            "    GOBACK.\n"
            "2000-READ-RECORD.\n"
            "    ADD 1 TO WS-COUNT.\n",
            header,
        )
        assert not result.backend_diagnostics
        java_file = tmp_path / "Texe4.java"
        java_file.write_text(result.java_source, encoding="utf-8")

        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe4"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        assert run.stdout.strip() == "000"
