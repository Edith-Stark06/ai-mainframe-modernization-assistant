"""Tests for Business Rule Extractor."""

from app.analysis.rules.extractor import BusinessRuleExtractor
from app.parser.ast.program import ProgramNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.statements import (
    IfStatementNode,
    MoveStatementNode,
    DisplayStatementNode,
    StatementNode,
    AddStatementNode,
)
from app.parser.lexer.position import Position


def _pos() -> Position:
    return Position(line=1, column=1, offset=0, filename="test.cbl")


def _prog(statements: tuple[StatementNode, ...]) -> ProgramNode:
    para = ParagraphNode(
        start_position=_pos(),
        end_position=_pos(),
        name="TEST-PARA",
        statements=statements,
    )
    proc = ProcedureDivisionNode(
        start_position=_pos(),
        end_position=_pos(),
        paragraphs=(para,),
    )
    return ProgramNode(
        start_position=_pos(), end_position=_pos(), procedure_division=proc
    )


def test_extract_empty_input() -> None:
    """An empty program produces no rules."""
    prog = ProgramNode(start_position=_pos(), end_position=_pos())
    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 0


def test_extract_top_level_actions_ignored() -> None:
    """Top-level actions without conditions do not form business rules."""
    move = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="1", target="X"
    )
    prog = _prog((move,))
    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 0


def test_extract_simple_if() -> None:
    """A simple IF statement produces one rule."""
    pos = _pos()
    move = MoveStatementNode(
        start_position=pos, end_position=pos, source="1", target="X"
    )
    if_stmt = IfStatementNode(
        start_position=pos,
        end_position=pos,
        condition_left="A",
        condition_operator=">",
        condition_right="B",
        then_statements=(move,),
    )
    prog = _prog((if_stmt,))

    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 1
    assert rules[0].condition == "A > B"
    assert rules[0].actions == ("MOVE 1 TO X",)
    assert rules[0].source_location == pos


def test_extract_if_else() -> None:
    """An IF/ELSE statement produces two rules."""
    move1 = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="1", target="X"
    )
    move2 = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="2", target="Y"
    )
    if_stmt = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="A",
        condition_operator="=",
        condition_right="B",
        then_statements=(move1,),
        else_statements=(move2,),
    )
    prog = _prog((if_stmt,))

    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 2
    assert rules[0].condition == "A = B"
    assert rules[0].actions == ("MOVE 1 TO X",)
    assert rules[1].condition == "NOT (A = B)"
    assert rules[1].actions == ("MOVE 2 TO Y",)


def test_extract_multiple_actions() -> None:
    """Multiple actions in a block are grouped into one rule."""
    move = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="1", target="X"
    )
    disp = DisplayStatementNode(
        start_position=_pos(), end_position=_pos(), operand='"HELLO"'
    )
    add = AddStatementNode(
        start_position=_pos(), end_position=_pos(), left="2", right="Z"
    )
    if_stmt = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="A",
        condition_operator="<",
        condition_right="10",
        then_statements=(move, disp, add),
    )
    prog = _prog((if_stmt,))

    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 1
    assert rules[0].actions == ("MOVE 1 TO X", 'DISPLAY "HELLO"', "ADD 2 TO Z")


def test_extract_nested_if() -> None:
    """Nested IF statements combine conditions."""
    inner_move = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="9", target="Y"
    )
    inner_if = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="C",
        condition_operator="=",
        condition_right="D",
        then_statements=(inner_move,),
    )
    outer_if = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="A",
        condition_operator=">",
        condition_right="B",
        then_statements=(inner_if,),
    )
    prog = _prog((outer_if,))

    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 1
    assert rules[0].condition == "A > B AND C = D"
    assert rules[0].actions == ("MOVE 9 TO Y",)


def test_extract_nested_if_else() -> None:
    """Complex nested IF/ELSE statements."""
    move_then = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="1", target="X"
    )
    move_else = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="2", target="Y"
    )
    outer_else = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="3", target="Z"
    )
    inner_if = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="C",
        condition_operator="=",
        condition_right="D",
        then_statements=(move_then,),
        else_statements=(move_else,),
    )
    outer_if = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="A",
        condition_operator=">",
        condition_right="B",
        then_statements=(inner_if,),
        else_statements=(outer_else,),
    )
    prog = _prog((outer_if,))

    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 3
    assert rules[0].condition == "A > B AND C = D"
    assert rules[0].actions == ("MOVE 1 TO X",)
    assert rules[1].condition == "A > B AND NOT (C = D)"
    assert rules[1].actions == ("MOVE 2 TO Y",)
    assert rules[2].condition == "NOT (A > B)"
    assert rules[2].actions == ("MOVE 3 TO Z",)


def test_extract_deterministic_ordering() -> None:
    """Extraction ordering matches AST order deterministically."""
    move1 = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="1", target="A"
    )
    if1 = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="1",
        condition_operator="=",
        condition_right="1",
        then_statements=(move1,),
    )

    move2 = MoveStatementNode(
        start_position=_pos(), end_position=_pos(), source="2", target="B"
    )
    if2 = IfStatementNode(
        start_position=_pos(),
        end_position=_pos(),
        condition_left="2",
        condition_operator="=",
        condition_right="2",
        then_statements=(move2,),
    )

    prog = _prog((if1, if2))
    extractor = BusinessRuleExtractor()
    rules = extractor.extract(prog)
    assert len(rules) == 2
    assert rules[0].condition == "1 = 1"
    assert rules[0].actions == ("MOVE 1 TO A",)
    assert rules[1].condition == "2 = 2"
    assert rules[1].actions == ("MOVE 2 TO B",)
