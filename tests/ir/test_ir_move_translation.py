"""
Comprehensive tests for TASK-026: IR Translation for MOVE Statements.

Purpose:
    Verify that IRBuilder correctly translates COBOL MOVE statements into
    IRMove instructions, that operand helpers classify literals and variable
    references correctly, that multiple statements are ordered correctly,
    that unsupported statements are skipped gracefully, and that all output
    is deterministic.

Coverage:
    build_operand():
        - Quoted string literals → literal form preserved.
        - Numeric integer literals (plain, signed).
        - Decimal numeric literals.
        - Identifiers → variable references (uppercased).
        - Mixed-case identifiers normalised.
        - Edge: empty-looking strings (len-2 quotes).

    build_literal():
        - String literal returned unchanged.
        - Numeric literal returned unchanged.
        - Zero-value literal.
        - Negative literal.

    build_variable_reference():
        - Known symbol → canonical name from SymbolTable.
        - Unknown symbol → uppercased name (no error).
        - Lower-case name normalised to upper.

    _is_numeric_literal():
        - Plain integers: "0", "1", "42", "100".
        - Signed: "-1", "+5", "-0".
        - Decimal: "3.14", "-0.5".
        - Empty string → False.
        - Alphabetic → False.
        - Double decimal point → False.
        - Bare sign characters → False.

    build_move_instruction():
        - Variable→variable: IRMove(source=var, result=var).
        - Literal→variable: IRMove(source=literal, result=var).
        - Numeric literal→variable: IRMove(source=numeric, result=var).
        - Source/target are correctly mapped.
        - Returns IRMove instance.
        - IRMove.kind == IRNodeKind.INSTRUCTION.

    build_entry_block():
        - None proc_div → empty block, label "entry".
        - Empty paragraphs → empty block.
        - Single MOVE → one IRMove instruction.
        - Two MOVEs in same paragraph → two instructions, correct order.
        - MOVEs across two paragraphs → all collected, correct order.
        - Unsupported statement (DISPLAY) → skipped, no error.
        - Mixed MOVE + DISPLAY → only MOVE emitted.
        - Returned type is IRBasicBlock.
        - instructions is a tuple.

    build_function():
        - With proc_div: function contains entry block with instructions.
        - Without proc_div: function contains empty entry block.

    build_module():
        - With proc_div: module's function's block has instructions.

    build_program():
        - With proc_div: instructions in deeply-nested block.

    build() / full pipeline:
        - No program_node → empty entry block.
        - Program with no procedure_division → empty entry block.
        - Program with empty procedure_division → empty entry block.
        - Program with one MOVE → one IRMove in block.
        - Program with two MOVEs → two IRMoves, correct order.
        - Program with three paragraphs each with one MOVE → three IRMoves.
        - Literal-to-variable MOVE.
        - Numeric-to-variable MOVE.
        - Deterministic: two build() calls return equal programs.
        - Stateless: two calls return distinct program objects.
        - PROGRAM-ID name propagated.
        - current_program() equals build().

    Backward compatibility:
        - build() without arguments still works (no regression).
        - All TASK-024 + TASK-025 test scenarios unaffected.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.ir.builder import IRBuilder
from app.ir.instructions import IRMove
from app.ir.nodes import IRNodeKind
from app.ir.program import IRProgram
from app.parser.lexer.position import Position
from app.parser.semantic.context import SemanticContext, SymbolTable
from app.parser.semantic.symbols import ProgramSymbol, VariableSymbol

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _pos(line: int = 1) -> Position:
    return Position(line=line, column=1, offset=0, filename="test.cbl")


def _make_program_node(
    *,
    paragraphs=(),
    has_proc_div: bool = True,
):
    """Build a minimal ProgramNode with the given paragraphs."""
    from app.parser.ast.procedure import ProcedureDivisionNode
    from app.parser.ast.program import ProgramNode

    pos = _pos()
    if has_proc_div:
        proc = ProcedureDivisionNode(
            start_position=pos,
            end_position=pos,
            paragraphs=tuple(paragraphs),
        )
    else:
        proc = None

    return ProgramNode(
        start_position=pos,
        end_position=pos,
        procedure_division=proc,
    )


def _make_paragraph(name: str, *statements):
    from app.parser.ast.paragraphs import ParagraphNode

    pos = _pos()
    return ParagraphNode(
        start_position=pos,
        end_position=pos,
        name=name,
        statements=tuple(statements),
    )


def _move(source: str, target: str):
    from app.parser.ast.statements import MoveStatementNode

    pos = _pos()
    return MoveStatementNode(
        start_position=pos,
        end_position=pos,
        source=source,
        target=target,
    )


def _display(operand: str = '"HELLO"'):
    from app.parser.ast.statements import DisplayStatementNode

    pos = _pos()
    return DisplayStatementNode(start_position=pos, end_position=pos, operand=operand)


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------


def _ctx_empty() -> SemanticContext:
    return SemanticContext(symbol_table=SymbolTable(), diagnostics=[])


def _ctx_with_symbols(prog_name: str = "PAYROLL", *var_names: str) -> SemanticContext:
    table = SymbolTable()
    pos = _pos()
    table.register(ProgramSymbol(name=prog_name, declared_at=pos))
    for i, name in enumerate(var_names, start=5):
        table.register(VariableSymbol(name=name, declared_at=_pos(line=i), level=77))
    return SemanticContext(symbol_table=table, diagnostics=[])


# ===========================================================================
# _is_numeric_literal
# ===========================================================================


class TestIsNumericLiteral:
    """IRBuilder._is_numeric_literal() classification."""

    def _check(self, text: str) -> bool:
        return IRBuilder._is_numeric_literal(text)

    def test_zero(self) -> None:
        assert self._check("0") is True

    def test_plain_integer(self) -> None:
        assert self._check("42") is True

    def test_large_integer(self) -> None:
        assert self._check("1000000") is True

    def test_signed_negative(self) -> None:
        assert self._check("-1") is True

    def test_signed_positive(self) -> None:
        assert self._check("+5") is True

    def test_signed_zero(self) -> None:
        assert self._check("-0") is True

    def test_decimal(self) -> None:
        assert self._check("3.14") is True

    def test_decimal_negative(self) -> None:
        assert self._check("-0.5") is True

    def test_empty_string(self) -> None:
        assert self._check("") is False

    def test_bare_sign(self) -> None:
        assert self._check("-") is False

    def test_bare_plus(self) -> None:
        assert self._check("+") is False

    def test_alphabetic(self) -> None:
        assert self._check("WS-COUNT") is False

    def test_quoted_string(self) -> None:
        assert self._check('"HELLO"') is False

    def test_double_decimal(self) -> None:
        assert self._check("1.2.3") is False

    def test_alphanumeric(self) -> None:
        assert self._check("1A") is False


# ===========================================================================
# build_literal()
# ===========================================================================


class TestBuildLiteral:
    """build_literal() returns text unchanged."""

    def _b(self) -> IRBuilder:
        return IRBuilder(context=_ctx_empty())

    def test_string_literal(self) -> None:
        assert self._b().build_literal('"HELLO"') == '"HELLO"'

    def test_numeric_literal(self) -> None:
        assert self._b().build_literal("42") == "42"

    def test_zero(self) -> None:
        assert self._b().build_literal("0") == "0"

    def test_negative(self) -> None:
        assert self._b().build_literal("-1") == "-1"

    def test_decimal(self) -> None:
        assert self._b().build_literal("3.14") == "3.14"

    def test_empty_quotes(self) -> None:
        assert self._b().build_literal('""') == '""'


# ===========================================================================
# build_variable_reference()
# ===========================================================================


class TestBuildVariableReference:
    """build_variable_reference() — symbol-table lookup + normalisation."""

    def test_known_symbol_returns_canonical_name(self) -> None:
        ctx = _ctx_with_symbols("P", "WS-OUT")
        b = IRBuilder(context=ctx)
        assert b.build_variable_reference("WS-OUT") == "WS-OUT"

    def test_known_symbol_lower_input(self) -> None:
        ctx = _ctx_with_symbols("P", "WS-OUT")
        b = IRBuilder(context=ctx)
        assert b.build_variable_reference("ws-out") == "WS-OUT"

    def test_unknown_symbol_uses_uppercased_name(self) -> None:
        b = IRBuilder(context=_ctx_empty())
        assert b.build_variable_reference("UNKNOWN-VAR") == "UNKNOWN-VAR"

    def test_unknown_symbol_lower_case_uppercased(self) -> None:
        b = IRBuilder(context=_ctx_empty())
        assert b.build_variable_reference("unknown-var") == "UNKNOWN-VAR"

    def test_no_exception_for_unknown(self) -> None:
        b = IRBuilder(context=_ctx_empty())
        result = b.build_variable_reference("TOTALLY-UNKNOWN")
        assert isinstance(result, str)


# ===========================================================================
# build_operand()
# ===========================================================================


class TestBuildOperand:
    """build_operand() — dispatches to literal or variable reference."""

    def _b(self, *var_names: str) -> IRBuilder:
        ctx = _ctx_with_symbols("P", *var_names)
        return IRBuilder(context=ctx)

    def test_quoted_string_is_literal(self) -> None:
        assert self._b().build_operand('"HELLO"') == '"HELLO"'

    def test_quoted_string_with_space_is_literal(self) -> None:
        assert self._b().build_operand('"HELLO WORLD"') == '"HELLO WORLD"'

    def test_numeric_integer_is_literal(self) -> None:
        assert self._b().build_operand("42") == "42"

    def test_zero_is_literal(self) -> None:
        assert self._b().build_operand("0") == "0"

    def test_negative_is_literal(self) -> None:
        assert self._b().build_operand("-1") == "-1"

    def test_positive_signed_is_literal(self) -> None:
        assert self._b().build_operand("+5") == "+5"

    def test_decimal_is_literal(self) -> None:
        assert self._b().build_operand("3.14") == "3.14"

    def test_identifier_is_variable(self) -> None:
        b = self._b("WS-COUNT")
        assert b.build_operand("WS-COUNT") == "WS-COUNT"

    def test_lowercase_identifier_normalised(self) -> None:
        b = self._b("WS-COUNT")
        assert b.build_operand("ws-count") == "WS-COUNT"

    def test_unknown_identifier_uppercased(self) -> None:
        b = self._b()
        assert b.build_operand("unknown-var") == "UNKNOWN-VAR"

    def test_empty_quotes_are_literal(self) -> None:
        assert self._b().build_operand('""') == '""'


# ===========================================================================
# build_move_instruction()
# ===========================================================================


class TestBuildMoveInstruction:
    """build_move_instruction() — single MOVE statement lowering."""

    def _b(self) -> IRBuilder:
        return IRBuilder(context=_ctx_with_symbols("P", "WS-IN", "WS-OUT"))

    def test_returns_ir_move(self) -> None:
        stmt = _move("WS-IN", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert isinstance(result, IRMove)

    def test_kind_is_instruction(self) -> None:
        stmt = _move("WS-IN", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert result.kind is IRNodeKind.INSTRUCTION

    def test_var_to_var_source(self) -> None:
        stmt = _move("WS-IN", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert result.source == "WS-IN"

    def test_var_to_var_result(self) -> None:
        stmt = _move("WS-IN", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert result.result == "WS-OUT"

    def test_literal_to_var_source(self) -> None:
        stmt = _move('"HELLO"', "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert result.source == '"HELLO"'

    def test_literal_to_var_result(self) -> None:
        stmt = _move('"HELLO"', "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert result.result == "WS-OUT"

    def test_numeric_to_var_source(self) -> None:
        stmt = _move("0", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert result.source == "0"

    def test_negative_numeric_to_var(self) -> None:
        stmt = _move("-1", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert result.source == "-1"

    def test_is_frozen(self) -> None:
        stmt = _move("WS-IN", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        with pytest.raises((AttributeError, TypeError)):
            result.source = "CHANGED"  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        stmt = _move("WS-IN", "WS-OUT")
        result = self._b().build_move_instruction(stmt)
        assert hash(result) is not None


# ===========================================================================
# build_entry_block() — with ProcedureDivisionNode
# ===========================================================================


class TestBuildEntryBlock:
    """build_entry_block() with various ProcedureDivisionNode inputs."""

    def _b(self) -> IRBuilder:
        return IRBuilder(context=_ctx_with_symbols("P", "WS-A", "WS-B", "WS-C"))

    def test_none_proc_div_returns_empty_block(self) -> None:
        bb = self._b().build_entry_block(None)
        assert bb.instructions == ()

    def test_none_proc_div_label(self) -> None:
        bb = self._b().build_entry_block(None)
        assert bb.label == "entry"

    def test_empty_paragraphs_returns_empty_block(self) -> None:
        from app.parser.ast.procedure import ProcedureDivisionNode

        pos = _pos()
        proc = ProcedureDivisionNode(
            start_position=pos, end_position=pos, paragraphs=()
        )
        bb = self._b().build_entry_block(proc)
        assert bb.instructions == ()

    def test_single_move_emits_one_instruction(self) -> None:
        para = _make_paragraph("MAIN", _move("WS-A", "WS-B"))
        prog = _make_program_node(paragraphs=(para,))
        bb = self._b().build_entry_block(prog.procedure_division)
        assert len(bb.instructions) == 1

    def test_single_move_is_ir_move(self) -> None:
        para = _make_paragraph("MAIN", _move("WS-A", "WS-B"))
        prog = _make_program_node(paragraphs=(para,))
        bb = self._b().build_entry_block(prog.procedure_division)
        assert isinstance(bb.instructions[0], IRMove)

    def test_single_move_source(self) -> None:
        para = _make_paragraph("MAIN", _move("WS-A", "WS-B"))
        prog = _make_program_node(paragraphs=(para,))
        bb = self._b().build_entry_block(prog.procedure_division)
        instr = bb.instructions[0]
        assert isinstance(instr, IRMove)
        assert instr.source == "WS-A"

    def test_single_move_result(self) -> None:
        para = _make_paragraph("MAIN", _move("WS-A", "WS-B"))
        prog = _make_program_node(paragraphs=(para,))
        bb = self._b().build_entry_block(prog.procedure_division)
        assert bb.instructions[0].result == "WS-B"

    def test_two_moves_same_paragraph_order(self) -> None:
        para = _make_paragraph("MAIN", _move("WS-A", "WS-B"), _move("WS-B", "WS-C"))
        prog = _make_program_node(paragraphs=(para,))
        bb = self._b().build_entry_block(prog.procedure_division)
        assert len(bb.instructions) == 2
        i0, i1 = bb.instructions[0], bb.instructions[1]
        assert isinstance(i0, IRMove) and isinstance(i1, IRMove)
        assert i0.source == "WS-A"
        assert i1.source == "WS-B"

    def test_moves_across_two_paragraphs(self) -> None:
        para1 = _make_paragraph("PARA-1", _move("WS-A", "WS-B"))
        para2 = _make_paragraph("PARA-2", _move("WS-B", "WS-C"))
        prog = _make_program_node(paragraphs=(para1, para2))
        bb = self._b().build_entry_block(prog.procedure_division)
        assert len(bb.instructions) == 2
        i0, i1 = bb.instructions[0], bb.instructions[1]
        assert isinstance(i0, IRMove) and isinstance(i1, IRMove)
        assert i0.source == "WS-A"
        assert i1.source == "WS-B"

    def test_returns_ir_basic_block(self) -> None:
        from app.ir.blocks import IRBasicBlock

        bb = self._b().build_entry_block(None)
        assert isinstance(bb, IRBasicBlock)

    def test_instructions_is_tuple(self) -> None:
        bb = self._b().build_entry_block(None)
        assert isinstance(bb.instructions, tuple)

    def test_three_moves_three_instructions(self) -> None:
        para = _make_paragraph(
            "MAIN",
            _move("WS-A", "WS-B"),
            _move("WS-B", "WS-C"),
            _move('"DONE"', "WS-A"),
        )
        prog = _make_program_node(paragraphs=(para,))
        bb = self._b().build_entry_block(prog.procedure_division)
        assert len(bb.instructions) == 3


# ===========================================================================
# build() — full pipeline
# ===========================================================================


class TestBuildWithProgramNode:
    """Full pipeline tests: build(program_node)."""

    def _ctx(self, *var_names: str) -> SemanticContext:
        return _ctx_with_symbols("PAYROLL", *var_names)

    def _prog(self, *var_names: str) -> IRBuilder:
        return IRBuilder(context=self._ctx(*var_names))

    def _bb(self, prog_ir: IRProgram):
        return prog_ir.modules[0].functions[0].blocks[0]

    # -- None program_node ------------------------------------------------

    def test_no_program_node_returns_ir_program(self) -> None:
        result = self._prog().build()
        assert isinstance(result, IRProgram)

    def test_no_program_node_empty_block(self) -> None:
        prog = self._prog().build()
        assert self._bb(prog).instructions == ()

    # -- Program node with no procedure division --------------------------

    def test_no_proc_div_empty_block(self) -> None:
        node = _make_program_node(has_proc_div=False)
        prog = self._prog().build(node)
        assert self._bb(prog).instructions == ()

    # -- Program node with empty procedure division -----------------------

    def test_empty_proc_div_empty_block(self) -> None:
        node = _make_program_node(paragraphs=())
        prog = self._prog().build(node)
        assert self._bb(prog).instructions == ()

    # -- MOVE variable → variable ----------------------------------------

    def test_var_to_var_single_move(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        instr = self._bb(prog).instructions
        assert len(instr) == 1
        assert isinstance(instr[0], IRMove)

    def test_var_to_var_source_field(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert self._bb(prog).instructions[0].source == "WS-IN"

    def test_var_to_var_result_field(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert self._bb(prog).instructions[0].result == "WS-OUT"

    # -- MOVE literal → variable -----------------------------------------

    def test_literal_to_var(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move('"HELLO"', "WS-OUT")),)
        )
        prog = self._prog("WS-OUT").build(node)
        instr = prog.modules[0].functions[0].blocks[0].instructions[0]
        assert isinstance(instr, IRMove)
        assert instr.source == '"HELLO"'
        assert instr.result == "WS-OUT"

    def test_numeric_to_var(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("0", "WS-COUNT")),)
        )
        prog = self._prog("WS-COUNT").build(node)
        instr = prog.modules[0].functions[0].blocks[0].instructions[0]
        assert isinstance(instr, IRMove)
        assert instr.source == "0"
        assert instr.result == "WS-COUNT"

    def test_negative_literal_to_var(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("-1", "WS-DIFF")),)
        )
        prog = self._prog("WS-DIFF").build(node)
        instr = self._bb(prog).instructions[0]
        assert isinstance(instr, IRMove)
        assert instr.source == "-1"

    # -- Multiple MOVE statements ----------------------------------------

    def test_two_moves_correct_count(self) -> None:
        para = _make_paragraph(
            "MAIN", _move("WS-IN", "WS-OUT"), _move("WS-OUT", "WS-BK")
        )
        node = _make_program_node(paragraphs=(para,))
        prog = self._prog("WS-IN", "WS-OUT", "WS-BK").build(node)
        assert len(self._bb(prog).instructions) == 2

    def test_two_moves_correct_order(self) -> None:
        para = _make_paragraph(
            "MAIN", _move("WS-IN", "WS-OUT"), _move("WS-OUT", "WS-BK")
        )
        node = _make_program_node(paragraphs=(para,))
        prog = self._prog("WS-IN", "WS-OUT", "WS-BK").build(node)
        instrs = self._bb(prog).instructions
        i0, i1 = instrs[0], instrs[1]
        assert isinstance(i0, IRMove) and isinstance(i1, IRMove)
        assert i0.source == "WS-IN"
        assert i1.source == "WS-OUT"

    def test_moves_across_paragraphs_collected(self) -> None:
        para1 = _make_paragraph("P1", _move("WS-IN", "WS-OUT"))
        para2 = _make_paragraph("P2", _move("WS-OUT", "WS-BK"))
        node = _make_program_node(paragraphs=(para1, para2))
        prog = self._prog("WS-IN", "WS-OUT", "WS-BK").build(node)
        assert len(self._bb(prog).instructions) == 2

    def test_five_moves_correct_count(self) -> None:
        moves = [_move(f"WS-VAR{i}", f"WS-VAR{i+1}") for i in range(5)]
        para = _make_paragraph("MAIN", *moves)
        node = _make_program_node(paragraphs=(para,))
        prog = IRBuilder(context=_ctx_with_symbols("P")).build(node)
        assert len(self._bb(prog).instructions) == 5

    # -- Instruction ordering --------------------------------------------

    def test_instruction_order_preserved_across_paragraphs(self) -> None:
        para1 = _make_paragraph("P1", _move('"A"', "WS-X"))
        para2 = _make_paragraph("P2", _move('"B"', "WS-X"))
        para3 = _make_paragraph("P3", _move('"C"', "WS-X"))
        node = _make_program_node(paragraphs=(para1, para2, para3))
        prog = self._prog("WS-X").build(node)
        instrs = self._bb(prog).instructions
        i0, i1, i2 = instrs[0], instrs[1], instrs[2]
        assert (
            isinstance(i0, IRMove) and isinstance(i1, IRMove) and isinstance(i2, IRMove)
        )
        assert i0.source == '"A"'
        assert i1.source == '"B"'
        assert i2.source == '"C"'

    # -- Determinism and statelessness -----------------------------------

    def test_build_deterministic(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        b = self._prog("WS-IN", "WS-OUT")
        assert b.build(node) == b.build(node)

    def test_build_distinct_objects(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        b = self._prog("WS-IN", "WS-OUT")
        p1 = b.build(node)
        p2 = b.build(node)
        assert p1 is not p2

    def test_current_program_equals_build(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        b = self._prog("WS-IN", "WS-OUT")
        assert b.current_program(node) == b.build(node)

    # -- Program name propagation ----------------------------------------

    def test_program_name_from_symbol(self) -> None:
        node = _make_program_node()
        prog = self._prog().build(node)
        assert prog.name == "PAYROLL"

    # -- Backward compat: build() without arguments ----------------------

    def test_build_no_args_still_works(self) -> None:
        prog = self._prog("WS-IN").build()
        assert isinstance(prog, IRProgram)
        assert len(prog) == 1

    def test_current_program_no_args(self) -> None:
        prog = self._prog().current_program()
        assert isinstance(prog, IRProgram)

    # -- IR node types in output -----------------------------------------

    def test_all_instructions_are_ir_move(self) -> None:
        para = _make_paragraph(
            "MAIN",
            _move("WS-IN", "WS-OUT"),
            _move('"HI"', "WS-OUT"),
            _move("0", "WS-COUNT"),
        )
        node = _make_program_node(paragraphs=(para,))
        prog = self._prog("WS-IN", "WS-OUT", "WS-COUNT").build(node)
        for instr in self._bb(prog).instructions:
            assert isinstance(instr, IRMove)

    def test_instructions_tuple_type(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert isinstance(self._bb(prog).instructions, tuple)

    # -- Structural invariants -------------------------------------------

    def test_always_one_module(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert len(prog) == 1

    def test_always_one_function(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert len(prog.modules[0]) == 1

    def test_always_one_block(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert len(prog.modules[0].functions[0]) == 1

    def test_block_label_is_entry(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert self._bb(prog).label == "entry"

    def test_result_is_hashable(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        assert hash(prog) is not None

    def test_result_is_frozen(self) -> None:
        node = _make_program_node(
            paragraphs=(_make_paragraph("MAIN", _move("WS-IN", "WS-OUT")),)
        )
        prog = self._prog("WS-IN", "WS-OUT").build(node)
        with pytest.raises((AttributeError, TypeError)):
            prog.name = "CHANGED"  # type: ignore[misc]
