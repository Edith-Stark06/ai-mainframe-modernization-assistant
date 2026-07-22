"""
Comprehensive tests for TASK-028: IR Translation for Arithmetic Statements.

Purpose:
    Verify that IRBuilder correctly translates COBOL ADD, SUBTRACT, MULTIPLY,
    and DIVIDE statements into their corresponding IR instructions.
"""

from __future__ import annotations

import pytest

from app.ir.builder import IRBuilder
from app.ir.instructions import IRAdd, IRSubtract, IRMultiply, IRDivide
from app.ir.nodes import IRNodeKind
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.statements import (
    AddStatementNode,
    SubtractStatementNode,
    MultiplyStatementNode,
    DivideStatementNode,
)
from app.parser.lexer.position import Position
from app.parser.semantic.context import SemanticContext


@pytest.fixture
def mock_pos() -> Position:
    """Return a dummy position for AST nodes."""
    return Position(line=1, column=1, offset=0, filename="test.cbl")


@pytest.fixture
def empty_context() -> SemanticContext:
    """Return an empty semantic context."""
    from app.parser.semantic.context import SymbolTable

    return SemanticContext(symbol_table=SymbolTable(), diagnostics=[])


def test_build_add_instruction(
    mock_pos: Position, empty_context: SemanticContext
) -> None:
    builder = IRBuilder(context=empty_context)
    stmt = AddStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="10", right="WS-TOTAL"
    )
    instr = builder.build_add_instruction(stmt)

    assert isinstance(instr, IRAdd)
    assert instr.kind == IRNodeKind.INSTRUCTION
    assert instr.left == "10"
    assert instr.right == "WS-TOTAL"


def test_build_subtract_instruction(
    mock_pos: Position, empty_context: SemanticContext
) -> None:
    builder = IRBuilder(context=empty_context)
    stmt = SubtractStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="5", right="WS-TOTAL"
    )
    instr = builder.build_subtract_instruction(stmt)

    assert isinstance(instr, IRSubtract)
    assert instr.left == "5"
    assert instr.right == "WS-TOTAL"


def test_build_multiply_instruction(
    mock_pos: Position, empty_context: SemanticContext
) -> None:
    builder = IRBuilder(context=empty_context)
    stmt = MultiplyStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="WS-RATE", right="WS-TOTAL"
    )
    instr = builder.build_multiply_instruction(stmt)

    assert isinstance(instr, IRMultiply)
    assert instr.left == "WS-RATE"
    assert instr.right == "WS-TOTAL"


def test_build_divide_instruction(
    mock_pos: Position, empty_context: SemanticContext
) -> None:
    builder = IRBuilder(context=empty_context)
    stmt = DivideStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="2", right="WS-TOTAL"
    )
    instr = builder.build_divide_instruction(stmt)

    assert isinstance(instr, IRDivide)
    assert instr.left == "2"
    assert instr.right == "WS-TOTAL"


def test_build_entry_block_with_arithmetic(
    mock_pos: Position, empty_context: SemanticContext
) -> None:
    stmt1 = AddStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="1", right="WS-A"
    )
    stmt2 = SubtractStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="2", right="WS-B"
    )
    stmt3 = MultiplyStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="3", right="WS-C"
    )
    stmt4 = DivideStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="4", right="WS-D"
    )

    para = ParagraphNode(
        start_position=mock_pos,
        end_position=mock_pos,
        name="CALC-PARA",
        statements=(stmt1, stmt2, stmt3, stmt4),
    )
    proc_div = ProcedureDivisionNode(
        start_position=mock_pos,
        end_position=mock_pos,
        paragraphs=(para,),
    )

    builder = IRBuilder(context=empty_context)
    block = builder.build_entry_block(proc_div)

    assert len(block.instructions) == 4
    assert isinstance(block.instructions[0], IRAdd)
    assert isinstance(block.instructions[1], IRSubtract)
    assert isinstance(block.instructions[2], IRMultiply)
    assert isinstance(block.instructions[3], IRDivide)


def test_full_pipeline_arithmetic_translation(
    mock_pos: Position, empty_context: SemanticContext
) -> None:
    stmt = AddStatementNode(
        start_position=mock_pos, end_position=mock_pos, left="100", right="WS-AMOUNT"
    )
    para = ParagraphNode(
        start_position=mock_pos,
        end_position=mock_pos,
        name="MAIN",
        statements=(stmt,),
    )
    proc = ProcedureDivisionNode(
        start_position=mock_pos,
        end_position=mock_pos,
        paragraphs=(para,),
    )
    program_node = ProgramNode(
        start_position=mock_pos,
        end_position=mock_pos,
        procedure_division=proc,
    )

    builder = IRBuilder(context=empty_context)
    prog = builder.build(program_node)

    assert len(prog.modules) == 1
    assert len(prog.modules[0].functions) == 1
    assert len(prog.modules[0].functions[0].blocks) == 1

    bb = prog.modules[0].functions[0].blocks[0]
    assert len(bb.instructions) == 1
    assert isinstance(bb.instructions[0], IRAdd)
    assert bb.instructions[0].left == "100"
    assert bb.instructions[0].right == "WS-AMOUNT"
