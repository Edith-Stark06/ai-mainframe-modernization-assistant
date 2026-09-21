"""
Unit tests for IR translation of control flow statements (TASK-029).
"""

from app.ir.builder import IRBuilder
from app.ir.instructions import IRCall, IRElse, IREndIf, IRIf, IRJump, IRMove
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.statements import (
    IfStatementNode,
    PerformStatementNode,
    GoToStatementNode,
    MoveStatementNode,
)
from app.parser.semantic.context import SemanticContext, SymbolTable
from app.parser.lexer.position import Position

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _empty_ctx() -> SemanticContext:
    return SemanticContext(symbol_table=SymbolTable(), diagnostics=[])


def _move(source: str, target: str) -> MoveStatementNode:
    return MoveStatementNode(
        start_position=_POS, end_position=_POS, source=source, target=target
    )


def _if(
    left: str,
    then_stmts: list,
    else_stmts: list | None = None,
    operator: str = "=",
    right: str = "1",
) -> IfStatementNode:
    """Build ``IF <left> <operator> <right>`` -- the AST's condition is a
    ``(left, operator, right)`` triple since TASK-039 (it was one string in
    TASK-029, when these tests were written)."""
    return IfStatementNode(
        start_position=_POS,
        end_position=_POS,
        condition_left=left,
        condition_operator=operator,
        condition_right=right,
        then_statements=tuple(then_stmts),
        else_statements=tuple(else_stmts or []),
    )


def _perform(target: str) -> PerformStatementNode:
    return PerformStatementNode(start_position=_POS, end_position=_POS, target=target)


def _goto(target: str) -> GoToStatementNode:
    return GoToStatementNode(start_position=_POS, end_position=_POS, target=target)


def _make_program_node(paragraphs: list[ParagraphNode]) -> ProgramNode:
    proc = ProcedureDivisionNode(
        start_position=_POS, end_position=_POS, paragraphs=tuple(paragraphs)
    )
    return ProgramNode(
        start_position=_POS,
        end_position=_POS,
        identification_division=None,
        data_division=None,
        procedure_division=proc,
    )


class TestIRControlFlowTranslation:
    def test_perform_statement(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_perform("SUB-PARA"),),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))
        func = prog.modules[0].functions[0]
        assert len(func.blocks) == 1

        bb = func.blocks[0]
        assert len(bb.instructions) == 1
        call = bb.instructions[0]
        assert isinstance(call, IRCall)
        assert call.target == "SUB-PARA"

    def test_go_to_statement(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_goto("ERROR-PARA"),),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))
        func = prog.modules[0].functions[0]
        assert len(func.blocks) == 1

        bb = func.blocks[0]
        assert len(bb.instructions) == 1
        jmp = bb.instructions[0]
        assert isinstance(jmp, IRJump)
        assert jmp.target == "ERROR-PARA"

    # ------------------------------------------------------------------
    # IF lowers to a *structured* instruction sequence in one basic block:
    # IRIf ... [IRElse ...] IREndIf. (TASK-029 originally lowered IF to
    # separate then/else/merge blocks joined by IRConditionalBranch; the
    # structured form replaced it in TASK-039 and is what the CFG builder
    # and the Java backend consume today.)
    # ------------------------------------------------------------------

    def test_if_without_else(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(
                _if("WS-FLAG", [_move("1", "WS-OUT")]),
                _move("2", "WS-END"),
            ),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))
        func = prog.modules[0].functions[0]
        assert len(func.blocks) == 1

        instrs = func.blocks[0].instructions
        assert [type(i) for i in instrs] == [IRIf, IRMove, IREndIf, IRMove]

        branch = instrs[0]
        assert isinstance(branch, IRIf)
        assert (branch.left, branch.operator, branch.right) == ("WS-FLAG", "=", "1")
        assert branch.extra_terms == ()
        assert (instrs[1].source, instrs[1].result) == ("1", "WS-OUT")
        # the statement after END-IF is outside the conditional
        assert (instrs[3].source, instrs[3].result) == ("2", "WS-END")

    def test_if_with_else(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(
                _if("WS-FLAG", [_move("1", "WS-OUT")], [_move("0", "WS-OUT")]),
            ),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))
        func = prog.modules[0].functions[0]
        assert len(func.blocks) == 1

        instrs = func.blocks[0].instructions
        assert [type(i) for i in instrs] == [IRIf, IRMove, IRElse, IRMove, IREndIf]
        assert (instrs[0].left, instrs[0].operator, instrs[0].right) == (
            "WS-FLAG",
            "=",
            "1",
        )
        # then-branch precedes IRElse, else-branch follows it
        assert instrs[1].source == "1"
        assert instrs[3].source == "0"

    def test_nested_if(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_if("WS-FLAG1", [_if("WS-FLAG2", [_move("1", "WS-OUT")])]),),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))
        func = prog.modules[0].functions[0]
        assert len(func.blocks) == 1

        instrs = func.blocks[0].instructions
        # outer IF opens, inner IF opens/closes around the MOVE, outer closes
        assert [type(i) for i in instrs] == [IRIf, IRIf, IRMove, IREndIf, IREndIf]
        assert instrs[0].left == "WS-FLAG1"
        assert instrs[1].left == "WS-FLAG2"
        assert instrs[2].source == "1"
