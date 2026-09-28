"""
IR tests for task #stage34 — ``PerformVaryingStatementNode`` ->
``IRPerformVarying``/``IREndPerform`` lowering.

Purpose:
    Before this stage, ``PERFORM VARYING`` misparsed into
    ``PerformStatementNode(target="VARYING")``, which
    ``IRBuilder.build_perform_statement`` lowered into a flat
    ``IRCall(target="VARYING", comment="PERFORM")`` -- discarding the
    varying variable, FROM/BY/UNTIL, and the entire loop body. These
    tests lock in the real, structured ``IRPerformVarying`` lowering
    (item 17 of the task's test list: no ``IRCall(target="VARYING")``
    remains anywhere in the IR for a real ``PERFORM VARYING``), and that
    the loop body is recursively lowered exactly like ``PERFORM UNTIL``'s
    already is.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.ir.instructions import (
    IRAdd,
    IRCall,
    IREndPerform,
    IRMove,
    IRPerformVarying,
    IRSubscript,
)

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
    return AnalysisService().analyze_file(path)


def _instructions(result):
    return result.ir.modules[0].functions[0].blocks[0].instructions


class TestNoLegacyIRCall:
    def test_no_ircall_target_varying_remains(self, tmp_path: Path) -> None:
        """Item 17: the old misparse's IR shadow is gone."""
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        calls = [i for i in _instructions(result) if isinstance(i, IRCall)]
        assert not any(c.target == "VARYING" for c in calls)

    def test_irperformvarying_is_produced(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        loops = [i for i in _instructions(result) if isinstance(i, IRPerformVarying)]
        assert len(loops) == 1


class TestHeaderFields:
    def test_varying_variable_from_by_until(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        (loop,) = [i for i in _instructions(result) if isinstance(i, IRPerformVarying)]
        assert loop.varying_variable == "CURRENT-IDX"
        assert loop.from_value == "1"
        assert loop.by_value == "1"
        assert loop.left == "CURRENT-IDX"
        assert loop.operator == ">"
        assert loop.right == "4"

    def test_by_negative_literal(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 4 BY -1\n"
            "        UNTIL CURRENT-IDX < 1\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        (loop,) = [i for i in _instructions(result) if isinstance(i, IRPerformVarying)]
        assert loop.from_value == "4"
        assert loop.by_value == "-1"

    def test_subscripted_until_condition(self, tmp_path: Path) -> None:
        """The UNTIL condition gets subscript support through the same
        machinery IF uses, even though no real corpus occurrence needs
        it -- verified directly here."""
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL WS-ITEM(CURRENT-IDX) > 100\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        (loop,) = [i for i in _instructions(result) if isinstance(i, IRPerformVarying)]
        assert loop.left == "WS-ITEM"
        assert loop.left_subscript == (
            IRSubscript(kind="identifier", value="CURRENT-IDX"),
        )


class TestBodyLowering:
    def test_body_instructions_are_present_between_open_and_close(
        self, tmp_path: Path
    ) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        MOVE CURRENT-IDX TO WS-ITEM(CURRENT-IDX)\n"
            "        ADD 1 TO WS-TOTAL\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        instrs = _instructions(result)
        open_idx = next(
            i for i, x in enumerate(instrs) if isinstance(x, IRPerformVarying)
        )
        close_idx = next(i for i, x in enumerate(instrs) if isinstance(x, IREndPerform))
        body = instrs[open_idx + 1 : close_idx]
        assert any(isinstance(i, IRMove) for i in body)
        assert any(isinstance(i, IRAdd) for i in body)

    def test_closed_by_irendperform(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        instrs = _instructions(result)
        ends = [i for i in instrs if isinstance(i, IREndPerform)]
        assert len(ends) == 1

    def test_subscripted_body_move_target(self, tmp_path: Path) -> None:
        """Item 13-14: a subscripted body operand survives and uses
        Stage 32's structured IRSubscript, not a flattened string."""
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        MOVE CURRENT-IDX TO WS-ITEM(CURRENT-IDX)\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        (mv,) = [i for i in _instructions(result) if isinstance(i, IRMove)]
        assert mv.result == "WS-ITEM"
        assert mv.result_subscript == (
            IRSubscript(kind="identifier", value="CURRENT-IDX"),
        )


class TestScalarRegression:
    def test_plain_perform_until_ir_unaffected(self, tmp_path: Path) -> None:
        from app.ir.instructions import IRPerformUntil

        result = _analyze(
            tmp_path,
            "    PERFORM UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "        ADD 1 TO CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n",
        )
        loops = [i for i in _instructions(result) if isinstance(i, IRPerformUntil)]
        assert len(loops) == 1
        assert loops[0].left == "CURRENT-IDX"
        assert loops[0].operator == ">"
        assert loops[0].right == "4"
