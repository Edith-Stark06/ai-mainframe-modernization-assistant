"""
Division AST Node.

Purpose:
    Represent a single COBOL division (IDENTIFICATION, ENVIRONMENT, DATA,
    or PROCEDURE) within the Abstract Syntax Tree.

Responsibilities:
    - Record the division name.
    - Carry an ordered tuple of child AST nodes belonging to this division.
    - Implement :meth:`accept` for visitor-pattern dispatch.
    - Remain immutable after construction.

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of division contents.

Dependencies:
    - :mod:`app.parser.ast.node`          — ``ASTNode`` base class.
    - :mod:`app.parser.lexer.position`    — ``Position`` value type.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a division node::

        from app.parser.ast.division import DivisionNode
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        div = DivisionNode(
            start_position=pos,
            end_position=pos,
            name="IDENTIFICATION",
            children=(),
        )
        div.name  # "IDENTIFICATION"
        div.children  # ()

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.ast.node import ASTNode

__all__ = ["DivisionNode"]


@dataclass(frozen=True)
class DivisionNode(ASTNode):
    """
    Immutable AST node representing a single COBOL division.

    A COBOL program contains up to four divisions (IDENTIFICATION,
    ENVIRONMENT, DATA, PROCEDURE).  Each division is represented by
    one :class:`DivisionNode` that carries its name and an ordered
    tuple of child nodes (sections, paragraphs, statements) that are
    nested inside it.

    Attributes:
        start_position:
            Source position of the division's first token.
        end_position:
            Source position of the division's last token.
        name:
            The division name in uppercase (e.g. ``"IDENTIFICATION"``).
        children:
            Ordered tuple of :class:`~app.parser.ast.node.ASTNode`
            instances nested within this division.  Defaults to an empty
            tuple.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> div = DivisionNode(start_position=pos, end_position=pos,
        ...                    name="IDENTIFICATION", children=())
        >>> div.name
        'IDENTIFICATION'
        >>> div.children
        ()
    """

    name: str
    children: tuple[ASTNode, ...] = field(default_factory=tuple)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to :meth:`~app.parser.ast.visitor.ASTVisitor.visit_division`.

        Args:
            visitor: An :class:`~app.parser.ast.visitor.ASTVisitor`.

        Returns:
            The value returned by ``visitor.visit_division(self)``.
        """
        from app.parser.ast.visitor import ASTVisitor  # avoid circular import

        if isinstance(visitor, ASTVisitor):
            return visitor.visit_division(self)
        raise TypeError(
            f"Visitor must be an ASTVisitor, got {type(visitor).__name__!r}"
        )
