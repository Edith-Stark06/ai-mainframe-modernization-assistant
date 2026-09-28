"""
IR tests for task #stage38 — IF condition parenthesized
arithmetic-expression operand lowering.

Purpose:
    ``IRBuilder._lower_condition_operand``/``build_if_statement`` lower
    ``IfStatementNode.condition_left_expression``/
    ``condition_right_expression`` into ``IRIf.left_expression``/
    ``right_expression`` via :meth:`~app.ir.builder.IRBuilder
    .build_expression` — the exact same AST-to-IR expression lowering
    ``COMPUTE`` already uses, reused unchanged — so the structured tree
    survives into the IR rather than being flattened into a string.
    ``IRIf.condition_text()`` renders it back to source-equivalent text
    (via :func:`~app.ir.instructions.render_arithmetic_expression`, the
    same printer ``IRCompute.expression_text`` uses) for the CFG's
    decision-node labels.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.ir.instructions import IRBinaryExpression, IRIf, IROperandExpression

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\nWORKING-STORAGE SECTION.\n"

_HEADER = (
    "01 CURRENT-STOCK-QTY PIC 9(5) VALUE 120.\n"
    "01 SUGGESTED-ORDER-QTY PIC 9(5) VALUE 0.\n"
    "01 WAREHOUSE-CAPACITY PIC 9(5) VALUE 2000.\n"
    "01 SAFETY-STOCK-LEVEL PIC 9(5) VALUE 150.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    source = _ID + header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _instructions(result):
    return result.ir.modules[0].functions[0].blocks[0].instructions


class TestExpressionSurvivesLowering:
    def test_left_expression_is_structured_not_flattened(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        (instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert instr.left == ""
        assert instr.left_expression == IRBinaryExpression(
            operator="+",
            left=IROperandExpression(value="CURRENT-STOCK-QTY"),
            right=IROperandExpression(value="SUGGESTED-ORDER-QTY"),
        )
        assert instr.right == "WAREHOUSE-CAPACITY"
        assert instr.right_expression is None

    def test_right_expression_is_structured_not_flattened(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF CURRENT-STOCK-QTY < (SAFETY-STOCK-LEVEL / 2)\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        (instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert instr.left == "CURRENT-STOCK-QTY"
        assert instr.left_expression is None
        assert instr.right == ""
        assert instr.right_expression == IRBinaryExpression(
            operator="/",
            left=IROperandExpression(value="SAFETY-STOCK-LEVEL"),
            right=IROperandExpression(value="2"),
        )

    def test_no_garbage_identifier_or_string_token(self, tmp_path: Path) -> None:
        """The expression tree's leaves are real, individually-lowered
        operands -- never a combined/flattened string like
        "( CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY )"."""
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        (instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert instr.left_expression is not None
        assert isinstance(instr.left_expression, IRBinaryExpression)
        assert instr.left_expression.left.value == "CURRENT-STOCK-QTY"
        assert instr.left_expression.right.value == "SUGGESTED-ORDER-QTY"
        assert "(" not in instr.left_expression.left.value
        assert " " not in instr.left_expression.left.value


class TestConditionTextRendering:
    def test_condition_text_renders_the_expression(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        (instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert (
            instr.condition_text()
            == "(CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > WAREHOUSE-CAPACITY"
        )


class TestSerializationCompatibility:
    def test_plain_if_serializes_without_expression_fields(
        self, tmp_path: Path
    ) -> None:
        """A condition this stage does not change must not gain any new
        serialized field -- ``omit_if_empty`` keeps a plain IF's IR
        byte-identical to before this stage."""
        import dataclasses

        result = _analyze(
            tmp_path,
            "    IF CURRENT-STOCK-QTY > 0\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        (instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert instr.left_expression is None
        assert instr.right_expression is None
        # Every field flagged omit_if_empty (the whole point of this
        # convention) is genuinely falsy for an unaffected IF.
        for f in dataclasses.fields(instr):
            if f.metadata.get("omit_if_empty") and f.name in (
                "left_expression",
                "right_expression",
            ):
                assert not getattr(instr, f.name)


class TestScalarRegression:
    def test_subscripted_if_ir_unaffected(self, tmp_path: Path) -> None:
        from app.ir.instructions import IRSubscript

        result = _analyze(
            tmp_path,
            "    IF WS-ITEM(WS-I) > 100\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
            header=_HEADER
            + "01 WS-I PIC 9(2) VALUE 1.\n"
            + "01 WS-TABLE.\n    05 WS-ITEM PIC 9(3) OCCURS 4.\n",
        )
        (instr,) = [i for i in _instructions(result) if isinstance(i, IRIf)]
        assert instr.left == "WS-ITEM"
        assert instr.left_expression is None
        assert instr.left_subscript == (IRSubscript(kind="identifier", value="WS-I"),)

    def test_compute_ir_unaffected(self, tmp_path: Path) -> None:
        from app.ir.instructions import IRCompute

        result = _analyze(
            tmp_path,
            "    COMPUTE SUGGESTED-ORDER-QTY = CURRENT-STOCK-QTY + 1.\n"
            "    STOP RUN.\n",
        )
        (instr,) = [i for i in _instructions(result) if isinstance(i, IRCompute)]
        assert instr.expression == IRBinaryExpression(
            operator="+",
            left=IROperandExpression(value="CURRENT-STOCK-QTY"),
            right=IROperandExpression(value="1"),
        )
