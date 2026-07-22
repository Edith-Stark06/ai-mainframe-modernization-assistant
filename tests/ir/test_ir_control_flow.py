"""
Unit tests for IR translation of control flow statements (TASK-029).
"""


from app.ir.builder import IRBuilder
from app.ir.instructions import IRConditionalBranch, IRJump, IRCall, IRMove
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
    condition: str, then_stmts: list, else_stmts: list | None = None
) -> IfStatementNode:
    return IfStatementNode(
        start_position=_POS,
        end_position=_POS,
        condition=condition,
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
        # We expect 3 blocks: entry, then, merge
        assert len(func.blocks) == 3

        entry, then_block, merge_block = func.blocks

        assert entry.label == "entry"
        assert len(entry.instructions) == 1
        branch = entry.instructions[0]
        assert isinstance(branch, IRConditionalBranch)
        assert branch.condition == "WS-FLAG"
        assert branch.then_target == then_block.label
        assert branch.else_target == merge_block.label

        assert len(then_block.instructions) == 2
        assert isinstance(then_block.instructions[0], IRMove)
        assert then_block.instructions[0].source == "1"
        assert isinstance(then_block.instructions[1], IRJump)
        assert then_block.instructions[1].target == merge_block.label

        assert len(merge_block.instructions) == 1
        assert isinstance(merge_block.instructions[0], IRMove)
        assert merge_block.instructions[0].source == "2"

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
        # We expect 4 blocks: entry, then, else, merge
        assert len(func.blocks) == 4

        entry, then_block, else_block, merge_block = func.blocks

        assert entry.label == "entry"
        branch = entry.instructions[0]
        assert isinstance(branch, IRConditionalBranch)
        assert branch.then_target == then_block.label
        assert branch.else_target == else_block.label

        assert isinstance(then_block.instructions[0], IRMove)
        assert then_block.instructions[0].source == "1"
        assert isinstance(then_block.instructions[1], IRJump)
        assert then_block.instructions[1].target == merge_block.label

        assert isinstance(else_block.instructions[0], IRMove)
        assert else_block.instructions[0].source == "0"
        assert isinstance(else_block.instructions[1], IRJump)
        assert else_block.instructions[1].target == merge_block.label

    def test_nested_if(self) -> None:
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=(_if("WS-FLAG1", [_if("WS-FLAG2", [_move("1", "WS-OUT")])]),),
        )
        prog = IRBuilder(context=_empty_ctx()).build(_make_program_node([para]))
        func = prog.modules[0].functions[0]

        # entry -> branch1
        # then1 -> branch2
        # then2 -> move, jump merge2
        # merge2 -> jump merge1
        # merge1 -> empty
        assert len(func.blocks) == 5
        entry, then1, then2, merge2, merge1 = func.blocks

        assert isinstance(entry.instructions[0], IRConditionalBranch)
        assert entry.instructions[0].condition == "WS-FLAG1"
        assert entry.instructions[0].then_target == then1.label
        assert entry.instructions[0].else_target == merge1.label

        assert isinstance(then1.instructions[0], IRConditionalBranch)
        assert then1.instructions[0].condition == "WS-FLAG2"
        assert then1.instructions[0].then_target == then2.label
        assert then1.instructions[0].else_target == merge2.label
