"""
Tests for IR translation of COBOL CALL statements (TASK-030).
"""

from app.ir.builder import IRBuilder
from app.ir.instructions import IRCall, IRMove
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.statements import CallStatementNode, MoveStatementNode
from app.parser.lexer.position import Position
from app.parser.semantic.context import SemanticContext, SymbolTable

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _empty_ctx() -> SemanticContext:
    return SemanticContext(symbol_table=SymbolTable(), diagnostics=[])


def _call(target: str, arguments: tuple[str, ...] = ()) -> CallStatementNode:
    return CallStatementNode(
        start_position=_POS, end_position=_POS, target=target, arguments=arguments
    )


def _move(source: str, target: str) -> MoveStatementNode:
    return MoveStatementNode(
        start_position=_POS, end_position=_POS, source=source, target=target
    )


def _make_program_node(paragraphs: list[ParagraphNode]) -> ProgramNode:
    return ProgramNode(
        start_position=_POS,
        end_position=_POS,
        procedure_division=ProcedureDivisionNode(
            start_position=_POS,
            end_position=_POS,
            paragraphs=tuple(paragraphs),
        ),
    )


class TestIRCallTranslation:
    def test_call_literal(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_call('"SUBPROG"'),),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))

        func = prog.modules[0].functions[0]
        assert len(func.blocks) == 1
        block = func.blocks[0]
        assert len(block.instructions) == 1

        instr = block.instructions[0]
        assert isinstance(instr, IRCall)
        assert instr.target == "SUBPROG"
        assert instr.args == ()

    def test_call_identifier(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_call("WS-PROG-NAME"),),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))

        instr = prog.modules[0].functions[0].blocks[0].instructions[0]
        assert isinstance(instr, IRCall)
        assert instr.target == "WS-PROG-NAME"
        assert instr.args == ()

    def test_call_using(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_call('"CALC"', ("WS-A", "WS-B", "10")),),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))

        instr = prog.modules[0].functions[0].blocks[0].instructions[0]
        assert isinstance(instr, IRCall)
        assert instr.target == "CALC"
        assert instr.args == ("WS-A", "WS-B", "10")

    def test_mixed_statement_ordering(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(
                _move("1", "WS-A"),
                _call('"SUB"', ("WS-A",)),
                _move("WS-A", "WS-B"),
            ),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))

        block = prog.modules[0].functions[0].blocks[0]
        assert len(block.instructions) == 3

        assert isinstance(block.instructions[0], IRMove)
        assert isinstance(block.instructions[1], IRCall)
        assert isinstance(block.instructions[2], IRMove)

        call = block.instructions[1]
        assert call.target == "SUB"
        assert call.args == ("WS-A",)

    def test_missing_target_diagnostic(self) -> None:
        ctx = _empty_ctx()
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_call(""),),
        )
        prog = IRBuilder(context=ctx).build(_make_program_node([para]))

        block = prog.modules[0].functions[0].blocks[0]
        assert len(block.instructions) == 0

        assert len(ctx.diagnostics) == 1
        assert "Missing target" in ctx.diagnostics[0].message
