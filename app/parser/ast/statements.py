"""
Statement AST Nodes.

Purpose:
    Define the immutable AST nodes that represent individual executable
    COBOL statements parsed from the PROCEDURE DIVISION.

    Each node carries the structural tokens captured during parsing.
    Nodes are deliberately thin; semantic analysis is a separate concern.

Responsibilities:
    - Provide :class:`StatementNode` — the abstract base for all statement
      nodes.
    - Provide :class:`DisplayStatementNode` — a ``DISPLAY`` statement.
    - Provide :class:`MoveStatementNode`    — a ``MOVE ... TO ...`` statement.
    - Provide :class:`StopRunStatementNode` — a ``STOP RUN`` statement.
    - Provide :class:`GobackStatementNode`  — a ``GOBACK`` statement.
    - Remain immutable after construction (``frozen=True`` dataclasses).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation (data types, scope, etc.).
    - IF, EVALUATE, PERFORM, GO TO, CALL, COMPUTE, arithmetic statements.

Dependencies:
    - :mod:`app.parser.ast.node` — ``ASTNode`` base class.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a DISPLAY statement node::

        from app.parser.ast.statements import DisplayStatementNode
        from app.parser.lexer.position import Position

        pos = Position(line=10, column=4, offset=200, filename="prog.cbl")
        node = DisplayStatementNode(
            start_position=pos,
            end_position=pos,
            operand="\"HELLO\"",
        )
        node.operand  # '"HELLO"'

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.parser.ast.node import ASTNode

__all__ = [
    "AcceptStatementNode",
    "AddStatementNode",
    "CallStatementNode",
    "DisplayStatementNode",
    "DivideStatementNode",
    "GoToStatementNode",
    "GobackStatementNode",
    "IfStatementNode",
    "MoveStatementNode",
    "MultiplyStatementNode",
    "PerformStatementNode",
    "StatementNode",
    "StopRunStatementNode",
    "SubtractStatementNode",
]


@dataclass(frozen=True)
class StatementNode(ASTNode):
    """
    Abstract base for all PROCEDURE DIVISION statement nodes.

    Every concrete statement node inherits from this class and gains the
    standard ``start_position`` / ``end_position`` span from
    :class:`~app.parser.ast.node.ASTNode`.

    Concrete subclasses must implement :meth:`accept` to call the
    appropriate visitor method.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> # StatementNode is abstract — instantiate a concrete subclass.
    """

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_statement(self)`` if available.

        Concrete subclasses override this with a more specific method
        name.  The base implementation provides a fallback that works
        with any generic visitor.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class DisplayStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``DISPLAY`` statement.

    Captures all operand tokens from immediately after ``DISPLAY`` up to
    the terminating period as a single concatenated string.

    COBOL syntax example::

        DISPLAY "HELLO".
        DISPLAY WS-COUNT.

    Attributes:
        start_position:
            Source position of the ``DISPLAY`` keyword.
        end_position:
            Source position of the terminating period.
        operand:
            The raw operand text (e.g. ``'"HELLO"'``, ``'WS-COUNT'``).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=10, column=4, offset=200, filename="x.cbl")
        >>> node = DisplayStatementNode(
        ...     start_position=pos, end_position=pos, operand='"HELLO"',
        ... )
        >>> node.operand
        '"HELLO"'
    """

    operand: str

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_display_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_display_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class AcceptStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``ACCEPT`` statement.

    Captures the target operand token from immediately after ``ACCEPT`` up to
    the terminating period as a single string.

    COBOL syntax example::

        ACCEPT WS-DATE.
        ACCEPT WS-INPUT.

    Attributes:
        start_position:
            Source position of the ``ACCEPT`` keyword.
        end_position:
            Source position of the terminating period.
        target:
            The raw operand text (e.g. ``'WS-DATE'``).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=11, column=4, offset=220, filename="x.cbl")
        >>> node = AcceptStatementNode(
        ...     start_position=pos, end_position=pos, target="WS-DATE",
        ... )
        >>> node.target
        'WS-DATE'
    """

    target: str

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_accept_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_accept_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class MoveStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``MOVE ... TO ...`` statement.

    Captures the source operand (everything between ``MOVE`` and ``TO``)
    and the target operand (everything between ``TO`` and the period).

    COBOL syntax example::

        MOVE 1 TO WS-COUNT.
        MOVE WS-NAME TO DISPLAY-NAME.

    Attributes:
        start_position:
            Source position of the ``MOVE`` keyword.
        end_position:
            Source position of the terminating period.
        source:
            The source operand text (e.g. ``'1'``, ``'WS-NAME'``).
        target:
            The target data-name text (e.g. ``'WS-COUNT'``).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=5, column=4, offset=80, filename="x.cbl")
        >>> node = MoveStatementNode(
        ...     start_position=pos, end_position=pos,
        ...     source="1", target="WS-COUNT",
        ... )
        >>> node.source
        '1'
        >>> node.target
        'WS-COUNT'
    """

    source: str
    target: str

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_move_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_move_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class AddStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``ADD ... TO ...`` statement.
    """

    left: str
    right: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_add_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class SubtractStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``SUBTRACT ... FROM ...`` statement.
    """

    left: str
    right: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_subtract_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class MultiplyStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``MULTIPLY ... BY ...`` statement.
    """

    left: str
    right: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_multiply_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class DivideStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``DIVIDE ... INTO ...`` statement.
    """

    left: str
    right: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_divide_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class StopRunStatementNode(StatementNode):
    """
    Immutable AST node for the COBOL ``STOP RUN`` statement.

    ``STOP RUN`` terminates program execution and transfers control
    back to the operating system.

    COBOL syntax example::

        STOP RUN.

    Attributes:
        start_position:
            Source position of the ``STOP`` keyword.
        end_position:
            Source position of the terminating period.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=20, column=4, offset=400, filename="x.cbl")
        >>> node = StopRunStatementNode(start_position=pos, end_position=pos)
    """

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_stop_run_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_stop_run_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class GobackStatementNode(StatementNode):
    """
    Immutable AST node for the COBOL ``GOBACK`` statement.

    ``GOBACK`` transfers control back to the caller of the current
    program or sub-program.

    COBOL syntax example::

        GOBACK.

    Attributes:
        start_position:
            Source position of the ``GOBACK`` keyword or identifier.
        end_position:
            Source position of the terminating period.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=25, column=4, offset=500, filename="x.cbl")
        >>> node = GobackStatementNode(start_position=pos, end_position=pos)
    """

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_goback_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_goback_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IfStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``IF`` statement.
    """

    condition: str
    then_statements: tuple[StatementNode, ...]
    else_statements: tuple[StatementNode, ...] = ()

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_if_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class PerformStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``PERFORM`` statement.
    """

    target: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_perform_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class GoToStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``GO TO`` statement.
    """

    target: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_go_to_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class CallStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``CALL`` statement.
    """

    target: str
    arguments: tuple[str, ...] = ()

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_call_statement", None)
        if callable(visit):
            return visit(self)
        return None
