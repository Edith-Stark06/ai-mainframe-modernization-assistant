"""
Tests for the COBOL AST Foundation Models.

Purpose:
    Verify that the AST node hierarchy is correctly structured,
    immutable, and that the visitor pattern dispatches correctly.

Coverage:
    - ASTNode abstract base class (inheritance, immutability).
    - DivisionNode construction, name, children, accept().
    - ProgramNode construction, optional divisions, accept().
    - ASTVisitor default (no-op) behaviour.
    - ASTVisitor subclass override behaviour.
    - ParserProtocol structural compatibility check.
    - ParserError attributes and formatting.

Non-responsibilities:
    - Parsing or lexical analysis.
    - Concrete visitor analysis logic (belongs in application tests).

Dependencies:
    - :mod:`app.parser.ast.node`                    — ASTNode.
    - :mod:`app.parser.ast.division`                — DivisionNode.
    - :mod:`app.parser.ast.program`                 — ProgramNode.
    - :mod:`app.parser.ast.visitor`                 — ASTVisitor.
    - :mod:`app.parser.syntax.parser_interfaces`    — ParserProtocol.
    - :mod:`app.parser.syntax.parser_exceptions`    — ParserError.
    - :mod:`app.parser.lexer.position`              — Position.
    - :mod:`pytest`                                 — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses

import pytest

from app.parser.ast.division import DivisionNode
from app.parser.ast.node import ASTNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.visitor import ASTVisitor
from app.parser.lexer.position import Position
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_interfaces import ParserProtocol

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")
_END = Position(line=5, column=20, offset=100, filename="test.cbl")


def make_division(name: str, children: tuple = ()) -> DivisionNode:
    return DivisionNode(
        start_position=_POS,
        end_position=_END,
        name=name,
        children=children,
    )


def make_program(**kwargs: DivisionNode | None) -> ProgramNode:
    return ProgramNode(
        start_position=_POS,
        end_position=_END,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# ASTNode (abstract base class)
# ---------------------------------------------------------------------------


class TestASTNode:
    """ASTNode is abstract and cannot be instantiated directly."""

    def test_astnode_is_abstract(self) -> None:
        """ASTNode cannot be instantiated — it is abstract."""
        with pytest.raises(TypeError):
            ASTNode(start_position=_POS, end_position=_END)  # type: ignore[abstract]

    def test_division_node_is_astnode(self) -> None:
        """DivisionNode inherits from ASTNode."""
        div = make_division("IDENTIFICATION")
        assert isinstance(div, ASTNode)

    def test_program_node_is_astnode(self) -> None:
        """ProgramNode inherits from ASTNode."""
        prog = make_program()
        assert isinstance(prog, ASTNode)

    def test_start_position_stored(self) -> None:
        div = make_division("PROCEDURE")
        assert div.start_position == _POS

    def test_end_position_stored(self) -> None:
        div = make_division("PROCEDURE")
        assert div.end_position == _END


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    """All AST nodes are frozen dataclasses — mutation raises FrozenInstanceError."""

    def test_division_node_is_frozen(self) -> None:
        div = make_division("IDENTIFICATION")
        with pytest.raises(dataclasses.FrozenInstanceError):
            div.name = "OTHER"  # type: ignore[misc]

    def test_program_node_is_frozen(self) -> None:
        prog = make_program()
        with pytest.raises(dataclasses.FrozenInstanceError):
            prog.identification_division = make_division("ID")  # type: ignore[misc]

    def test_division_children_tuple_is_immutable(self) -> None:
        """Children field is a tuple — tuples are immutable."""
        div = make_division("DATA", children=())
        assert isinstance(div.children, tuple)

    def test_division_node_hashable(self) -> None:
        """Frozen dataclasses are hashable."""
        div = make_division("IDENTIFICATION")
        assert hash(div) is not None
        assert {div}  # can be placed in a set

    def test_program_node_hashable(self) -> None:
        prog = make_program()
        assert hash(prog) is not None


# ---------------------------------------------------------------------------
# DivisionNode
# ---------------------------------------------------------------------------


class TestDivisionNode:
    """DivisionNode construction and field access."""

    def test_name_stored(self) -> None:
        div = make_division("ENVIRONMENT")
        assert div.name == "ENVIRONMENT"

    def test_empty_children_default(self) -> None:
        div = make_division("DATA")
        assert div.children == ()

    def test_children_stored(self) -> None:
        child = make_division("CHILD")
        div = make_division("PARENT", children=(child,))
        assert len(div.children) == 1
        assert div.children[0] is child

    def test_multiple_children(self) -> None:
        c1 = make_division("C1")
        c2 = make_division("C2")
        c3 = make_division("C3")
        div = make_division("PARENT", children=(c1, c2, c3))
        assert len(div.children) == 3

    def test_equality(self) -> None:
        d1 = make_division("IDENTIFICATION")
        d2 = make_division("IDENTIFICATION")
        assert d1 == d2

    def test_inequality_by_name(self) -> None:
        d1 = make_division("IDENTIFICATION")
        d2 = make_division("PROCEDURE")
        assert d1 != d2

    def test_all_division_names(self) -> None:
        """All four standard division names can be stored."""
        for name in ("IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE"):
            div = make_division(name)
            assert div.name == name


# ---------------------------------------------------------------------------
# ProgramNode
# ---------------------------------------------------------------------------


class TestProgramNode:
    """ProgramNode construction and optional division fields."""

    def test_all_divisions_none_by_default(self) -> None:
        prog = make_program()
        assert prog.identification_division is None
        assert prog.environment_division is None
        assert prog.data_division is None
        assert prog.procedure_division is None

    def test_identification_division_stored(self) -> None:
        div = make_division("IDENTIFICATION")
        prog = make_program(identification_division=div)
        assert prog.identification_division is div

    def test_environment_division_stored(self) -> None:
        div = make_division("ENVIRONMENT")
        prog = make_program(environment_division=div)
        assert prog.environment_division is div

    def test_data_division_stored(self) -> None:
        div = make_division("DATA")
        prog = make_program(data_division=div)
        assert prog.data_division is div

    def test_procedure_division_stored(self) -> None:
        div = make_division("PROCEDURE")
        prog = make_program(procedure_division=div)
        assert prog.procedure_division is div

    def test_all_divisions_present(self) -> None:
        """A program can hold all four divisions simultaneously."""
        prog = ProgramNode(
            start_position=_POS,
            end_position=_END,
            identification_division=make_division("IDENTIFICATION"),
            environment_division=make_division("ENVIRONMENT"),
            data_division=make_division("DATA"),
            procedure_division=make_division("PROCEDURE"),
        )
        assert prog.identification_division is not None
        assert prog.environment_division is not None
        assert prog.data_division is not None
        assert prog.procedure_division is not None

    def test_program_equality(self) -> None:
        p1 = make_program()
        p2 = make_program()
        assert p1 == p2


# ---------------------------------------------------------------------------
# ASTVisitor — default behaviour
# ---------------------------------------------------------------------------


class TestASTVisitorDefaults:
    """The default ASTVisitor methods are no-ops returning None."""

    def _noop_visitor(self) -> ASTVisitor:
        class Noop(ASTVisitor):
            pass

        return Noop()

    def test_visit_program_returns_none_by_default(self) -> None:
        visitor = self._noop_visitor()
        prog = make_program()
        result = visitor.visit_program(prog)
        assert result is None

    def test_visit_division_returns_none_by_default(self) -> None:
        visitor = self._noop_visitor()
        div = make_division("IDENTIFICATION")
        result = visitor.visit_division(div)
        assert result is None


# ---------------------------------------------------------------------------
# ASTVisitor — dispatch via accept()
# ---------------------------------------------------------------------------


class TestVisitorDispatch:
    """accept() correctly dispatches to the visitor's visit_* methods."""

    def _collecting_visitor(self) -> ASTVisitor:
        class Collector(ASTVisitor):
            def __init__(self) -> None:
                self.programs_visited: list[ProgramNode] = []
                self.divisions_visited: list[DivisionNode] = []

            def visit_program(self, node: ProgramNode) -> None:
                self.programs_visited.append(node)

            def visit_division(self, node: DivisionNode) -> None:
                self.divisions_visited.append(node)

        return Collector()

    def test_program_accept_calls_visit_program(self) -> None:
        visitor = self._collecting_visitor()
        prog = make_program()
        prog.accept(visitor)
        assert len(visitor.programs_visited) == 1  # type: ignore[attr-defined]
        assert visitor.programs_visited[0] is prog  # type: ignore[attr-defined]

    def test_division_accept_calls_visit_division(self) -> None:
        visitor = self._collecting_visitor()
        div = make_division("PROCEDURE")
        div.accept(visitor)
        assert len(visitor.divisions_visited) == 1  # type: ignore[attr-defined]
        assert visitor.divisions_visited[0] is div  # type: ignore[attr-defined]

    def test_multiple_divisions_all_dispatched(self) -> None:
        visitor = self._collecting_visitor()
        for name in ("IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE"):
            make_division(name).accept(visitor)
        assert len(visitor.divisions_visited) == 4  # type: ignore[attr-defined]

    def test_accept_returns_visitor_result(self) -> None:
        """accept() returns whatever the visitor method returns."""

        class ReturningVisitor(ASTVisitor):
            def visit_program(self, node: ProgramNode) -> str:
                return "PROGRAM_VISITED"

            def visit_division(self, node: DivisionNode) -> str:
                return f"DIVISION:{node.name}"

        visitor = ReturningVisitor()
        prog = make_program()
        assert prog.accept(visitor) == "PROGRAM_VISITED"

        div = make_division("DATA")
        assert div.accept(visitor) == "DIVISION:DATA"

    def test_accept_non_visitor_raises(self) -> None:
        """accept() with a non-ASTVisitor raises TypeError."""
        div = make_division("IDENTIFICATION")
        with pytest.raises(TypeError):
            div.accept("not a visitor")  # type: ignore[arg-type]

    def test_program_accept_non_visitor_raises(self) -> None:
        prog = make_program()
        with pytest.raises(TypeError):
            prog.accept(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ParserProtocol structural check
# ---------------------------------------------------------------------------


class TestParserProtocol:
    """ParserProtocol is a runtime-checkable structural Protocol."""

    def test_class_with_parse_satisfies_protocol(self) -> None:
        class ConcreteParser:
            def parse(self, tokens: list) -> ProgramNode:  # type: ignore[override]
                return make_program()

        assert isinstance(ConcreteParser(), ParserProtocol)

    def test_class_without_parse_does_not_satisfy_protocol(self) -> None:
        class NotAParser:
            pass

        assert not isinstance(NotAParser(), ParserProtocol)


# ---------------------------------------------------------------------------
# ParserError
# ---------------------------------------------------------------------------


class TestParserError:
    """ParserError carries message and position attributes."""

    def test_message_stored(self) -> None:
        err = ParserError("unexpected token")
        assert err.message == "unexpected token"

    def test_line_stored(self) -> None:
        err = ParserError("err", line=5)
        assert err.line == 5

    def test_column_stored(self) -> None:
        err = ParserError("err", column=12)
        assert err.column == 12

    def test_offset_stored(self) -> None:
        err = ParserError("err", offset=99)
        assert err.offset == 99

    def test_defaults_are_zero(self) -> None:
        err = ParserError("err")
        assert err.line == 0
        assert err.column == 0
        assert err.offset == 0

    def test_str_includes_position(self) -> None:
        err = ParserError("unexpected token", line=3, column=5, offset=42)
        assert "3" in str(err)
        assert "5" in str(err)

    def test_is_exception(self) -> None:
        err = ParserError("err")
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(ParserError) as exc_info:
            raise ParserError("bad token", line=1, column=1, offset=0)
        assert exc_info.value.message == "bad token"
