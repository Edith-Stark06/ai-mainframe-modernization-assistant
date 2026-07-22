"""
Comprehensive tests for TASK-027: IR Translation for DISPLAY and ACCEPT Statements.

Purpose:
    Verify that IRBuilder correctly translates COBOL DISPLAY and ACCEPT statements
    into IRDisplay and IRAccept instructions. Verify operand helpers are reused,
    symbols are resolved, diagnostics are emitted (via logs), and that multiple
    mixed instructions (MOVE, DISPLAY, ACCEPT) are appended in source order.
"""

import pytest

from app.ir.builder import IRBuilder
from app.ir.instructions import IRAccept, IRDisplay, IRMove
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.statements import (
    AcceptStatementNode,
    DisplayStatementNode,
    MoveStatementNode,
    StopRunStatementNode,
)
from app.parser.lexer.position import Position
from app.parser.semantic.context import SemanticContext, SymbolTable
from app.parser.semantic.symbols import VariableSymbol


@pytest.fixture
def empty_context() -> SemanticContext:
    """Provide a valid, empty SemanticContext."""
    return SemanticContext(symbol_table=SymbolTable(), diagnostics=[])


@pytest.fixture
def context_with_vars() -> SemanticContext:
    """Provide a SemanticContext with pre-registered variables."""
    table = SymbolTable()
    pos = Position(1, 1, 0, "x.cbl")
    table.register(VariableSymbol(name="WS-INPUT", declared_at=pos, level=1))
    table.register(VariableSymbol(name="WS-OUTPUT", declared_at=pos, level=1))
    return SemanticContext(symbol_table=table, diagnostics=[])


@pytest.fixture
def pos() -> Position:
    """Provide a dummy source position."""
    return Position(line=10, column=4, offset=100, filename="test.cbl")


class TestIRBuilderIOTranslation:
    # -- DISPLAY Translation ---------------------------------------------------

    def test_build_display_instruction_string_literal(
        self, empty_context: SemanticContext, pos: Position
    ):
        """Translate a DISPLAY with a string literal operand."""
        builder = IRBuilder(empty_context)
        stmt = DisplayStatementNode(
            start_position=pos, end_position=pos, operand='"HELLO WORLD"'
        )

        instr = builder.build_display_instruction(stmt)

        assert isinstance(instr, IRDisplay)
        assert instr.operand == '"HELLO WORLD"'
        assert instr.result == ""

    def test_build_display_instruction_numeric_literal(
        self, empty_context: SemanticContext, pos: Position
    ):
        """Translate a DISPLAY with a numeric literal operand."""
        builder = IRBuilder(empty_context)
        stmt = DisplayStatementNode(
            start_position=pos, end_position=pos, operand="-42.5"
        )

        instr = builder.build_display_instruction(stmt)

        assert isinstance(instr, IRDisplay)
        assert instr.operand == "-42.5"
        assert instr.result == ""

    def test_build_display_instruction_variable(
        self, context_with_vars: SemanticContext, pos: Position
    ):
        """Translate a DISPLAY with a variable reference, resolving it in the symbol table."""
        builder = IRBuilder(context_with_vars)
        stmt = DisplayStatementNode(
            start_position=pos, end_position=pos, operand="ws-output"
        )

        instr = builder.build_display_instruction(stmt)

        assert isinstance(instr, IRDisplay)
        assert instr.operand == "WS-OUTPUT"
        assert instr.result == ""

    # -- ACCEPT Translation ----------------------------------------------------

    def test_build_accept_instruction_variable(
        self, context_with_vars: SemanticContext, pos: Position
    ):
        """Translate an ACCEPT into a variable reference."""
        builder = IRBuilder(context_with_vars)
        stmt = AcceptStatementNode(
            start_position=pos, end_position=pos, target=" ws-input "
        )

        instr = builder.build_accept_instruction(stmt)

        assert isinstance(instr, IRAccept)
        assert instr.result == "WS-INPUT"

    # -- Paragraph Translation -------------------------------------------------

    def test_translate_statement_dispatch(
        self, empty_context: SemanticContext, pos: Position
    ):
        """Ensure _translate_statement dispatches properly."""
        builder = IRBuilder(empty_context)

        disp = DisplayStatementNode(start_position=pos, end_position=pos, operand='"A"')
        acc = AcceptStatementNode(start_position=pos, end_position=pos, target="VAR")
        unsupported = StopRunStatementNode(start_position=pos, end_position=pos)

        # pylint: disable=protected-access
        res_disp = builder._translate_statement(disp)
        res_acc = builder._translate_statement(acc)
        res_uns = builder._translate_statement(unsupported)

        assert isinstance(res_disp, IRDisplay)
        assert isinstance(res_acc, IRAccept)
        assert res_uns is None

    # -- Mixed Order and Block Integration -------------------------------------

    def test_mixed_move_display_accept_ordering(
        self, context_with_vars: SemanticContext, pos: Position
    ):
        """
        Verify that a paragraph with multiple statement types correctly
        lowers all supported statements and appends them to the basic block
        in source order.
        """
        builder = IRBuilder(context_with_vars)

        stmt1 = AcceptStatementNode(
            start_position=pos, end_position=pos, target="WS-INPUT"
        )
        stmt2 = DisplayStatementNode(
            start_position=pos, end_position=pos, operand='"ACCEPTED:"'
        )
        stmt3 = DisplayStatementNode(
            start_position=pos, end_position=pos, operand="WS-INPUT"
        )
        stmt4 = MoveStatementNode(
            start_position=pos, end_position=pos, source="WS-INPUT", target="WS-OUTPUT"
        )
        stmt5 = StopRunStatementNode(
            start_position=pos, end_position=pos
        )  # Unsupported, will be skipped

        para = ParagraphNode(
            start_position=pos,
            end_position=pos,
            name="MAIN-PROC",
            statements=(stmt1, stmt2, stmt3, stmt4, stmt5),
        )
        proc_div = ProcedureDivisionNode(
            start_position=pos, end_position=pos, paragraphs=(para,)
        )
        program = ProgramNode(
            start_position=pos, end_position=pos, procedure_division=proc_div
        )

        ir_program = builder.build(program)
        block = ir_program.modules[0].functions[0].blocks[0]

        assert len(block.instructions) == 4

        i0 = block.instructions[0]
        i1 = block.instructions[1]
        i2 = block.instructions[2]
        i3 = block.instructions[3]

        assert isinstance(i0, IRAccept)
        assert i0.result == "WS-INPUT"

        assert isinstance(i1, IRDisplay)
        assert i1.operand == '"ACCEPTED:"'

        assert isinstance(i2, IRDisplay)
        assert i2.operand == "WS-INPUT"

        assert isinstance(i3, IRMove)
        assert i3.source == "WS-INPUT"
        assert i3.result == "WS-OUTPUT"

    def test_deterministic_ir_generation(
        self, empty_context: SemanticContext, pos: Position
    ):
        """Verify repeated builds with the same AST yield identical IR structures."""
        builder = IRBuilder(empty_context)

        stmt1 = DisplayStatementNode(
            start_position=pos, end_position=pos, operand='"A"'
        )
        stmt2 = AcceptStatementNode(start_position=pos, end_position=pos, target="VAR")

        para = ParagraphNode(
            start_position=pos, end_position=pos, name="P1", statements=(stmt1, stmt2)
        )
        proc_div = ProcedureDivisionNode(
            start_position=pos, end_position=pos, paragraphs=(para,)
        )
        program = ProgramNode(
            start_position=pos, end_position=pos, procedure_division=proc_div
        )

        prog1 = builder.build(program)
        prog2 = builder.build(program)

        assert prog1 == prog2
        assert id(prog1) != id(prog2)
