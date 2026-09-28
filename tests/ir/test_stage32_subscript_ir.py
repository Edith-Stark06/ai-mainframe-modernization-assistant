"""
Stage 32 — structured subscript representation in the IR layer.

Purpose:
    Lock in that ``IRMove``/``IRAdd``/``IRSubtract``/``IRMultiply``/
    ``IRDivide``/``IRDisplay``/``IRIf`` carry a structured
    ``IRSubscript`` (never a flattened string) for a subscripted
    operand, that the subscript's own value is looked up through the
    same symbol-table canonicalisation every other identifier operand
    gets, and that a plain (unsubscripted) program's IR is unaffected.

    Java-array lowering (turning a subscript into a Java index
    expression) is explicitly out of this stage's scope (Stage 33); see
    ``tests/parser/test_stage32_occurs_subscripts.py`` for the AST-level
    tests this file's IR-level tests build on.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.serializers.ir import serialize_ir
from app.analysis.service import AnalysisService
from app.ir.instructions import (
    IRAdd,
    IRDisplay,
    IRIf,
    IRMove,
    IRSubscript,
)

_TABLE_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(5) OCCURS 5 TIMES.\n"
    "   05 WS-I PIC 9(2) VALUE 1.\n"
    "01 WS-TOTAL PIC 9(5).\n"
)


def _analyze(tmp_path: Path, body: str):
    path = tmp_path / "t.cbl"
    path.write_text(
        _TABLE_HEADER + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body, encoding="utf-8"
    )
    return AnalysisService().analyze_file(path)


def _instructions(result):
    return result.ir.modules[0].functions[0].blocks[0].instructions


class TestIRMoveSubscripts:
    def test_literal_subscript_on_result(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, "    MOVE 100 TO WS-ITEM(2).\n    STOP RUN.\n")
        (mv,) = [i for i in _instructions(result) if isinstance(i, IRMove)]
        assert mv.source == "100"
        assert mv.source_subscript == ()
        assert mv.result == "WS-ITEM"
        assert mv.result_subscript == (IRSubscript(kind="literal", value="2"),)

    def test_identifier_subscript_on_source_is_canonicalised(
        self, tmp_path: Path
    ) -> None:
        """The subscript's own identifier is resolved through the symbol
        table the same way any other operand is (task #stage32) -- here
        the lower-case form must come back canonical/upper-cased."""
        result = _analyze(
            tmp_path, "    MOVE WS-ITEM(ws-i) TO WS-TOTAL.\n    STOP RUN.\n"
        )
        (mv,) = [i for i in _instructions(result) if isinstance(i, IRMove)]
        assert mv.source == "WS-ITEM"
        assert mv.source_subscript == (IRSubscript(kind="identifier", value="WS-I"),)
        assert mv.result == "WS-TOTAL"
        assert mv.result_subscript == ()


class TestIRArithmeticSubscripts:
    def test_add_result_and_right_share_the_subscript(self, tmp_path: Path) -> None:
        """ADD's `right` operand doubles as `result` (the accumulator);
        both must carry the same subscript, not just one of them."""
        result = _analyze(tmp_path, "    ADD 1 TO WS-ITEM(WS-I).\n    STOP RUN.\n")
        (add,) = [i for i in _instructions(result) if isinstance(i, IRAdd)]
        expected = (IRSubscript(kind="identifier", value="WS-I"),)
        assert add.right_subscript == expected
        assert add.result_subscript == expected
        assert add.left_subscript == ()


class TestIRDisplaySubscript:
    def test_operand_subscript(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, "    DISPLAY WS-ITEM(WS-I).\n    STOP RUN.\n")
        (disp,) = [i for i in _instructions(result) if isinstance(i, IRDisplay)]
        assert disp.operand == "WS-ITEM"
        assert disp.operand_subscript == (IRSubscript(kind="identifier", value="WS-I"),)


class TestIRIfSubscript:
    def test_condition_left_subscript_and_condition_text(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF WS-ITEM(WS-I) > 100\n"
            "        DISPLAY 'HIGH'\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        (if_instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert if_instr.left == "WS-ITEM"
        assert if_instr.left_subscript == (
            IRSubscript(kind="identifier", value="WS-I"),
        )
        assert if_instr.condition_text() == "WS-ITEM(WS-I) > 100"

    def test_plain_condition_text_unchanged(self, tmp_path: Path) -> None:
        """Regression: an unsubscripted IF's condition_text() is
        byte-identical to before this stage."""
        result = _analyze(
            tmp_path,
            "    IF WS-TOTAL > 0\n        DISPLAY 'X'\n    END-IF.\n    STOP RUN.\n",
        )
        (if_instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert if_instr.condition_text() == "WS-TOTAL > 0"


class TestSerializationBackwardCompatibility:
    def test_unsubscripted_ir_serializes_without_new_fields(
        self, tmp_path: Path
    ) -> None:
        """``omit_if_empty`` keeps a plain program's serialized IR exactly
        as it was before this stage -- no ``*_subscript``/``result_subscript``
        key appears when there is nothing to carry."""
        result = _analyze(tmp_path, "    MOVE 5 TO WS-TOTAL.\n    STOP RUN.\n")
        (mv,) = [i for i in _instructions(result) if isinstance(i, IRMove)]
        data = serialize_ir(mv)
        assert "source_subscript" not in data
        assert "result_subscript" not in data

    def test_subscripted_ir_serializes_the_structured_reference(
        self, tmp_path: Path
    ) -> None:
        result = _analyze(tmp_path, "    MOVE 100 TO WS-ITEM(2).\n    STOP RUN.\n")
        (mv,) = [i for i in _instructions(result) if isinstance(i, IRMove)]
        data = serialize_ir(mv)
        assert data["result_subscript"] == [
            {"type": "IRSubscript", "kind": "literal", "value": "2"}
        ]
