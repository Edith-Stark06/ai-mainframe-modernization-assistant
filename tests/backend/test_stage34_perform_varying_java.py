"""
Java backend tests for task #stage34 — ``PERFORM VARYING`` -> Java ``for``
loop lowering.

Purpose:
    ``control_flow_emitter.emit_perform_varying`` translates a structured
    ``IRPerformVarying`` into a Java ``for (<init>; <continue>; <step>) {``
    header, closed by the same ``emit_end_perform`` an ``IRPerformUntil``
    already is. The loop's varying variable, FROM/BY operands, and UNTIL
    condition (including a subscripted operand) all go through the exact
    same shared renderers every other emitter uses --
    ``_render_reference``/``_translate_operand`` (task #stage33) and
    ``_build_condition`` (task #stage31/#stage32) -- never a second,
    loop-specific implementation.

Coverage (task's numbered items 8-10, 13-18):
    8. Simple loop emits Java.
    9. BY 1 -> correct increment.
    10. BY -1 -> correct decrement.
    13. Subscripted body operand survives.
    14. Identifier subscript uses the Stage 33 shared renderer.
    15. Varying variable uses existing Java naming (to_java_field_name).
    16. Loop condition uses the existing condition renderer/machinery.
    17. (IR-level; see tests/ir/test_stage34_perform_varying_ir.py)
    18. Scalar non-loop programs are byte-identical.
    Plus: a real runtime execution test (javac + java), an UNTIL operator
    inversion table (evidenced forms only), and Stage 31/33 regression
    checks.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analysis.service import AnalysisService

_TABLE_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 CURRENT-IDX PIC 9(2) VALUE 1.\n"
    "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(3) OCCURS 4.\n"
    "01 WS-TOTAL PIC 9(5).\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _TABLE_HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(
        header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body, encoding="utf-8"
    )
    result = AnalysisService().analyze_file(path)
    assert not result.backend_diagnostics, result.backend_diagnostics
    return result.java_source


class TestSimpleLoopEmission:
    def test_simple_loop_emits_for(self, tmp_path: Path) -> None:
        """Item 8: a simple PERFORM VARYING emits a real Java for loop."""
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "for (currentIdx = 1; currentIdx <= 4; currentIdx += 1) {" in java

    def test_by_one_increment(self, tmp_path: Path) -> None:
        """Item 9."""
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "currentIdx += 1)" in java

    def test_by_negative_one_decrement(self, tmp_path: Path) -> None:
        """Item 10: BY -1 -> currentIdx += -1 (never a second `-=` form)."""
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 4 BY -1\n"
            "        UNTIL CURRENT-IDX < 1\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "currentIdx += -1)" in java
        assert "-=" not in java

    def test_loop_closed_by_matching_brace(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert java.count("for (") == 1
        # Exactly one closing brace at the loop's own depth follows it,
        # with the DISPLAY body statement in between.
        for_idx = java.index("for (")
        close_idx = java.index("}", for_idx)
        assert "System.out.println(" in java[for_idx:close_idx]


class TestVaryingVariableNaming:
    def test_hyphenated_name_uses_existing_naming_rules(self, tmp_path: Path) -> None:
        """Item 15: CURRENT-IDX -> currentIdx via to_java_field_name."""
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "currentIdx" in java
        assert "CURRENT-IDX" not in java
        assert "current-idx" not in java


class TestSubscriptedBody:
    def test_subscripted_move_target_in_body(self, tmp_path: Path) -> None:
        """Item 13-14: identifier subscript in the loop body goes through
        Stage 33's shared renderer."""
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        MOVE CURRENT-IDX TO WS-ITEM(CURRENT-IDX)\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "wsItem[currentIdx - 1] = currentIdx;" in java

    def test_subscripted_arithmetic_in_body(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        ADD WS-ITEM(CURRENT-IDX) TO WS-TOTAL\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "wsTotal += wsItem[currentIdx - 1];" in java

    def test_subscripted_if_in_body_preserves_nesting(self, tmp_path: Path) -> None:
        """Item 11-12: nested IF/MOVE inside the loop body survive with
        correct Java nesting."""
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        IF WS-ITEM(CURRENT-IDX) > 100\n"
            "            MOVE 0 TO WS-ITEM(CURRENT-IDX)\n"
            "        END-IF\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "for (currentIdx = 1; currentIdx <= 4; currentIdx += 1) {" in java
        assert "if (wsItem[currentIdx - 1] > 100) {" in java
        assert "wsItem[currentIdx - 1] = 0;" in java
        # Nesting: the IF header must be indented one level deeper than the for.
        for_line = next(
            line for line in java.splitlines() if line.strip().startswith("for (")
        )
        if_line = next(
            line for line in java.splitlines() if line.strip().startswith("if (")
        )
        for_indent = len(for_line) - len(for_line.lstrip(" "))
        if_indent = len(if_line) - len(if_line.lstrip(" "))
        assert if_indent > for_indent


class TestUntilConditionInversion:
    """Only the two operators the task explicitly evidences/gives a rule
    for (`>` -> `<=`, `>=` -> `<`) get the simplified inverted form; every
    other operator falls back to the always-correct `!(...)` wrap already
    used by plain PERFORM UNTIL."""

    def test_greater_than_inverts_to_less_equal(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "currentIdx <= 4" in java

    def test_greater_equal_inverts_to_less_than(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX >= 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "currentIdx < 4" in java

    def test_less_than_falls_back_to_negated_wrap(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 4 BY -1\n"
            "        UNTIL CURRENT-IDX < 1\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "!(currentIdx < 1)" in java

    def test_equality_falls_back_to_negated_wrap(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX = 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "!(currentIdx == 4)" in java

    def test_subscripted_until_condition_uses_shared_renderer(
        self, tmp_path: Path
    ) -> None:
        """Item 16: the UNTIL condition renders a subscripted operand
        through the exact same shared machinery IF uses."""
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL WS-ITEM(CURRENT-IDX) > 100\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "wsItem[currentIdx - 1] <= 100" in java


class TestScalarAndStage33Regression:
    def test_scalar_program_unaffected(self, tmp_path: Path) -> None:
        """Item 18: a non-loop program is completely unaffected."""
        header = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\nWORKING-STORAGE SECTION.\n01 WS-A PIC 9(3).\n"
        java = _analyze(tmp_path, "    MOVE 5 TO WS-A.\n    STOP RUN.\n", header)
        assert "for (" not in java

    def test_plain_perform_until_unaffected(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    PERFORM UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "        ADD 1 TO CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        assert "while (!(currentIdx > 4)) {" in java
        assert "for (" not in java

    def test_stage33_array_declaration_unaffected(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    MOVE 5 TO WS-ITEM(1).\n    STOP RUN.\n",
        )
        assert "private int[] wsItem = new int[4];" in java

    def test_stage31_display_formatting_unaffected(self, tmp_path: Path) -> None:
        header = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\nWORKING-STORAGE SECTION.\n01 WS-COUNT PIC 9(3) VALUE 5.\n"
        java = _analyze(tmp_path, "    DISPLAY WS-COUNT.\n    STOP RUN.\n", header)
        assert 'System.out.println(String.format("%03d", wsCount));' in java


class TestRuntimeExecution:
    """A real runtime execution test (javac + java): javac success alone
    does not prove loop semantics are correct."""

    def test_loop_populates_and_sums_array(self, tmp_path: Path) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-I PIC 9(2).\n"
            "01 WS-ITEM PIC 9(3) OCCURS 3.\n"
            "01 WS-TOTAL PIC 9(5).\n"
        )
        java = _analyze(
            tmp_path,
            "    MOVE 0 TO WS-TOTAL.\n"
            "    PERFORM VARYING WS-I FROM 1 BY 1\n"
            "        UNTIL WS-I > 3\n"
            "        MOVE WS-I TO WS-ITEM(WS-I)\n"
            "    END-PERFORM.\n"
            "    PERFORM VARYING WS-I FROM 1 BY 1\n"
            "        UNTIL WS-I > 3\n"
            "        ADD WS-ITEM(WS-I) TO WS-TOTAL\n"
            "    END-PERFORM.\n"
            "    DISPLAY WS-TOTAL.\n"
            "    STOP RUN.\n",
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
        # 1 + 2 + 3 = 6, zero-padded to PIC 9(5).
        assert run.stdout.strip() == "00006"

    def test_by_negative_one_loop_iterates_correct_count(self, tmp_path: Path) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE2.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-I PIC 9(2).\n"
            "01 WS-COUNT PIC 9(2) VALUE 0.\n"
        )
        java = _analyze(
            tmp_path,
            "    PERFORM VARYING WS-I FROM 3 BY -1\n"
            "        UNTIL WS-I < 1\n"
            "        ADD 1 TO WS-COUNT\n"
            "    END-PERFORM.\n"
            "    DISPLAY WS-COUNT.\n"
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
        # 3, 2, 1 -> 3 iterations.
        assert run.stdout.strip() == "03"
