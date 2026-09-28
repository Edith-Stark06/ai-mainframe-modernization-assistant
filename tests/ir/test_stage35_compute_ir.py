"""
Stage 35 — IR lowering for COMPUTE.

Purpose:
    Lock in ``IRBuilder.build_compute_instruction``/``build_expression``:
    a ``ComputeStatementNode`` lowers to a single ``IRCompute`` whose
    ``expression`` is a structured ``IRArithmeticExpression`` tree (an
    ``IROperandExpression`` leaf or a nested ``IRBinaryExpression``), not
    a flattened string -- and every leaf operand goes through the exact
    same ``build_operand``/``build_subscripts`` every other arithmetic
    instruction's operand already does.

    Explicitly NOT covered here (see tests/parser/test_stage35_compute.py
    and tests/backend/test_stage35_compute_java.py):
    - Parser-level grammar coverage.
    - Java code generation.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.ir.instructions import (
    IRBinaryExpression,
    IRCompute,
    IROperandExpression,
    IRSubscript,
)
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.ir.builder import IRBuilder
from app.parser.syntax.program_parser import ProgramParser

_TABLE_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-A PIC 9(7)V99.\n"
    "01 WS-B PIC 9(7)V99.\n"
    "01 WS-C PIC 9(7)V99.\n"
    "01 WS-D PIC 9(7)V99.\n"
    "01 WS-I PIC 9(2) VALUE 1.\n"
    "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(5)V99 OCCURS 5.\n"
)


def _build_instructions(body: str, header: str = _TABLE_HEADER):
    source = header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    ctx = SemanticAnalyzer().analyse(program)
    ir_program = IRBuilder(context=ctx).build(program)
    block = ir_program.modules[0].functions[0].blocks[0]
    return list(block.instructions)


def _one_compute(body: str, header: str = _TABLE_HEADER) -> IRCompute:
    instrs = _build_instructions(body, header)
    (compute,) = [i for i in instrs if isinstance(i, IRCompute)]
    return compute


class TestFlatExpression:
    def test_simple_sum_is_a_binary_expression(self) -> None:
        compute = _one_compute("    COMPUTE WS-A = WS-B + WS-C.\n    STOP RUN.\n")
        assert compute.result == "WS-A"
        assert compute.result_subscript == ()
        assert compute.expression == IRBinaryExpression(
            operator="+",
            left=IROperandExpression(value="WS-B"),
            right=IROperandExpression(value="WS-C"),
        )

    def test_bare_literal_is_an_operand_leaf(self) -> None:
        compute = _one_compute("    COMPUTE WS-A = 42.\n    STOP RUN.\n")
        assert compute.expression == IROperandExpression(value="42")


class TestPrecedenceTreeShape:
    def test_multiply_binds_tighter_than_add(self) -> None:
        """B + C * D -> B + (C * D): the tree shape itself encodes
        precedence, not a flattened string."""
        compute = _one_compute(
            "    COMPUTE WS-A = WS-B + WS-C * WS-D.\n    STOP RUN.\n"
        )
        expr = compute.expression
        assert isinstance(expr, IRBinaryExpression)
        assert expr.operator == "+"
        assert expr.left == IROperandExpression(value="WS-B")
        assert expr.right == IRBinaryExpression(
            operator="*",
            left=IROperandExpression(value="WS-C"),
            right=IROperandExpression(value="WS-D"),
        )

    def test_explicit_parens_preserved_as_tree_shape(self) -> None:
        """(B + C) * D -- parens are represented purely by nesting; there
        is no separate "had explicit parens" flag anywhere in the IR."""
        compute = _one_compute(
            "    COMPUTE WS-A = (WS-B + WS-C) * WS-D.\n    STOP RUN.\n"
        )
        expr = compute.expression
        assert expr.operator == "*"
        assert expr.left == IRBinaryExpression(
            operator="+",
            left=IROperandExpression(value="WS-B"),
            right=IROperandExpression(value="WS-C"),
        )
        assert expr.right == IROperandExpression(value="WS-D")

    def test_expression_text_reconstructs_required_parens(self) -> None:
        """'*' binds tighter than '+', so the parens around the '+'
        sub-tree are semantically required and must be reconstructed
        from tree shape alone (there is no stored "had explicit parens"
        flag to merely echo)."""
        compute = _one_compute(
            "    COMPUTE WS-A = (WS-B + WS-C) * WS-D.\n    STOP RUN.\n"
        )
        assert compute.expression_text() == "(WS-B + WS-C) * WS-D"

    def test_expression_text_omits_unneeded_parens(self) -> None:
        """A + B * C needs no parens at all -- '*' already binds tighter,
        so the tree shape alone is unambiguous without them."""
        compute = _one_compute(
            "    COMPUTE WS-A = WS-B + WS-C * WS-D.\n    STOP RUN.\n"
        )
        assert compute.expression_text() == "WS-B + WS-C * WS-D"


class TestSubscriptLowering:
    def test_target_and_operand_subscripts_lower_to_irsubscript(self) -> None:
        """Reuses task #stage32/33's IRSubscript unchanged -- the 1-based
        value is carried through untouched; 0-based conversion is a Java
        backend concern, not this one."""
        compute = _one_compute(
            "    COMPUTE WS-ITEM(2) = WS-ITEM(1) * WS-I.\n    STOP RUN.\n"
        )
        assert compute.result == "WS-ITEM"
        assert compute.result_subscript == (IRSubscript(kind="literal", value="2"),)
        expr = compute.expression
        assert expr.operator == "*"
        assert expr.left == IROperandExpression(
            value="WS-ITEM", subscript=(IRSubscript(kind="literal", value="1"),)
        )
        assert expr.right == IROperandExpression(value="WS-I")

    def test_identifier_subscript_lowers_and_canonicalizes(self) -> None:
        compute = _one_compute(
            "    COMPUTE WS-A = WS-ITEM(WS-I) + WS-B.\n    STOP RUN.\n"
        )
        expr = compute.expression
        assert expr.left == IROperandExpression(
            value="WS-ITEM",
            subscript=(IRSubscript(kind="identifier", value="WS-I"),),
        )


class TestResultIsAlwaysAFreshAssignment:
    def test_result_equals_target_not_an_accumulator_pair(self) -> None:
        """Unlike IRAdd/IRSubtract/IRMultiply/IRDivide (result mirrors a
        second 'right' operand that is compound-assigned), IRCompute's
        result is simply the target -- there is no second flat operand
        at all, only the expression tree."""
        compute = _one_compute("    COMPUTE WS-A = WS-B + WS-C.\n    STOP RUN.\n")
        assert compute.result == "WS-A"
        assert not hasattr(compute, "left")
        assert not hasattr(compute, "right")
