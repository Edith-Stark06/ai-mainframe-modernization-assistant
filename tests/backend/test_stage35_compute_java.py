"""
Java backend tests for task #stage35 — ``COMPUTE`` -> Java assignment
lowering.

Purpose:
    ``statement_emitter.emit_compute`` translates a structured
    ``IRCompute`` into a Java assignment (``result = <expr>;``), never a
    compound assignment -- the expression tree is rendered by
    ``_translate_expression``, a precedence-climbing printer that
    inserts parentheses only where COBOL's (and Java's -- identical
    precedence for ``+ - * /``) evaluation order would otherwise change,
    reusing ``_translate_operand``/``_render_reference`` (task
    #stage32/33) for every leaf, exactly like every other emitter.

Coverage:
    Every synthetic form from the Stage 35 investigation report's
    synthetic probe matrix, plus subscripted target/operand rendering
    and a real runtime-execution test (javac + java).

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
    "01 A PIC 9(5)V99.\n"
    "01 B PIC 9(5)V99.\n"
    "01 C PIC 9(5)V99.\n"
    "01 D PIC 9(5)V99.\n"
    "01 IDX PIC 9(2).\n"
    "01 ARR-A PIC 9(5)V99 OCCURS 5.\n"
    "01 ARR-B PIC 9(5)V99 OCCURS 5.\n"
    "01 ARR-F PIC 9(5)V99 OCCURS 5.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(
        header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body, encoding="utf-8"
    )
    result = AnalysisService().analyze_file(path)
    assert not result.backend_diagnostics, result.backend_diagnostics
    return result.java_source


class TestSyntheticProbeMatrix:
    """Every form probed in the Stage 35 investigation report, now
    asserted against the real implementation's exact Java output."""

    def test_simple_sum(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    COMPUTE A = B + C.\n    STOP RUN.\n")
        assert "a = b + c;" in java

    def test_simple_product(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    COMPUTE A = B * C.\n    STOP RUN.\n")
        assert "a = b * c;" in java

    def test_simple_quotient(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    COMPUTE A = B / C.\n    STOP RUN.\n")
        assert "a = b / c;" in java

    def test_mixed_precedence_no_parens_needed(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    COMPUTE A = B + C * D.\n    STOP RUN.\n")
        assert "a = b + c * d;" in java

    def test_explicit_parens_preserved(self, tmp_path: Path) -> None:
        """The task's own worked example: COMPUTE A = B * (C + D).
        -> a = b * (c + d);"""
        java = _analyze(tmp_path, "    COMPUTE A = B * (C + D).\n    STOP RUN.\n")
        assert "a = b * (c + d);" in java

    def test_subscripted_target_and_operands(self, tmp_path: Path) -> None:
        """The task's own worked example: COMPUTE A(WS-I) = B(WS-I) * C.
        -> a[wsI - 1] = b[wsI - 1] * c; -- here with the corpus's own
        naming (ARRAY-F(IDX) = ARR-A(IDX) * ARR-B(IDX))."""
        java = _analyze(
            tmp_path,
            "    COMPUTE ARR-F(IDX) = ARR-A(IDX) * ARR-B(IDX).\n    STOP RUN.\n",
        )
        assert "arrF[idx - 1] = arrA[idx - 1] * arrB[idx - 1];" in java

    def test_bare_literal(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    COMPUTE A = 123.\n    STOP RUN.\n")
        assert "a = 123;" in java


class TestParenthesizationCorrectness:
    """Beyond the investigation's matrix: forms that specifically probe
    the precedence-climbing printer's correctness, not just coverage."""

    def test_left_associative_subtraction_needs_no_parens(self, tmp_path: Path) -> None:
        """A - B - C must render without parens -- Java's own left-to-
        right evaluation of equal-precedence '-' already matches COBOL's,
        so 'a - b - c' is correct as-is, not '(a - b) - c'."""
        java = _analyze(tmp_path, "    COMPUTE A = B - C - D.\n    STOP RUN.\n")
        assert "a = b - c - d;" in java
        assert "(b - c)" not in java

    def test_right_side_subtraction_of_subtraction_needs_parens(
        self, tmp_path: Path
    ) -> None:
        """A - (B - C): dropping the parens here would silently change
        the result under left-associativity (A - B - C != A - (B - C)),
        so they must be reconstructed even though the printer never
        stores "had explicit parens"."""
        java = _analyze(tmp_path, "    COMPUTE A = B - (C - D).\n    STOP RUN.\n")
        assert "a = b - (c - d);" in java

    def test_doubly_nested_parens(self, tmp_path: Path) -> None:
        """payroll_deduct.cbl:55's shape: the most complex expression in
        the real corpus."""
        java = _analyze(
            tmp_path,
            "    COMPUTE A = B * (0.03 + ((C - 3.00) * 0.50 / 100.00)).\n"
            "    STOP RUN.\n",
        )
        assert "a = b * (0.03 + (c - 3.00) * 0.50 / 100.00);" in java


class TestRuntimeExecution:
    """javac success alone does not prove arithmetic semantics are
    correct -- these actually run the generated program."""

    def test_parenthesized_expression_computes_correct_value(
        self, tmp_path: Path
    ) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 A PIC 9(5)V99.\n"
            "01 B PIC 9(5)V99 VALUE 10.\n"
            "01 C PIC 9(5)V99 VALUE 5.\n"
            "01 D PIC 9(5)V99 VALUE 2.\n"
        )
        java = _analyze(
            tmp_path,
            "    COMPUTE A = (B + C) * D.\n" "    DISPLAY A.\n" "    STOP RUN.\n",
            header,
        )
        java_file = tmp_path / "Texe.java"
        java_file.write_text(java, encoding="utf-8")

        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        # (10 + 5) * 2 = 30, zero-padded to PIC 9(5)V99 (00003000).
        assert run.stdout.strip() == "0003000"

    def test_subscripted_running_total_computes_correct_value(
        self, tmp_path: Path
    ) -> None:
        """table_indexed.cbl's real shape: a subscripted COMPUTE inside a
        PERFORM VARYING body, accumulating a running total."""
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE2.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-I PIC 9(2).\n"
            "01 REVENUE PIC 9(5) OCCURS 3.\n"
            "01 TOTAL-REVENUE PIC 9(7).\n"
        )
        java = _analyze(
            tmp_path,
            "    MOVE 100 TO REVENUE(1).\n"
            "    MOVE 200 TO REVENUE(2).\n"
            "    MOVE 300 TO REVENUE(3).\n"
            "    MOVE 0 TO TOTAL-REVENUE.\n"
            "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 3\n"
            "        COMPUTE TOTAL-REVENUE = TOTAL-REVENUE + REVENUE(WS-I)\n"
            "    END-PERFORM.\n"
            "    DISPLAY TOTAL-REVENUE.\n"
            "    STOP RUN.\n",
            header,
        )
        java_file = tmp_path / "Texe2.java"
        java_file.write_text(java, encoding="utf-8")

        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe2"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        # 100 + 200 + 300 = 600, zero-padded to PIC 9(7).
        assert run.stdout.strip() == "0000600"
