"""
Program AST Node.

Purpose:
    Represent an entire COBOL compilation unit (program) as the root node
    of the Abstract Syntax Tree.

Responsibilities:
    - Hold optional references to each of the four standard COBOL divisions.
    - Implement :meth:`accept` for visitor-pattern dispatch.
    - Remain immutable after construction.

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of the program structure.

Dependencies:
    - :mod:`app.parser.ast.node`          — ``ASTNode`` base class.
    - :mod:`app.parser.ast.division`      — ``DivisionNode``.
    - :mod:`app.parser.ast.data`          — ``DataDivisionNode``.
    - :mod:`app.parser.lexer.position`    — ``Position`` value type.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a program node::

        from app.parser.ast.program import ProgramNode
        from app.parser.ast.division import DivisionNode
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        ident_div = DivisionNode(
            start_position=pos,
            end_position=pos,
            name="IDENTIFICATION",
            children=(),
        )
        program = ProgramNode(
            start_position=pos,
            end_position=pos,
            identification_division=ident_div,
        )
        program.identification_division.name  # "IDENTIFICATION"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.parser.ast.data import DataDivisionNode
from app.parser.ast.division import DivisionNode
from app.parser.ast.node import ASTNode

__all__ = ["ProgramNode"]


@dataclass(frozen=True)
class ProgramNode(ASTNode):
    """
    Immutable root AST node representing an entire COBOL program.

    A :class:`ProgramNode` is the top-level container produced by the
    parser.  It holds optional references to each of the four standard
    COBOL divisions.  Any division that was not present in the source
    file is represented as ``None``.

    Attributes:
        start_position:
            Source position of the program's first token.
        end_position:
            Source position of the program's last token.
        identification_division:
            The IDENTIFICATION DIVISION node, or ``None`` if absent.
        environment_division:
            The ENVIRONMENT DIVISION node, or ``None`` if absent.
        data_division:
            The DATA DIVISION node, or ``None`` if absent.
        procedure_division:
            The PROCEDURE DIVISION node, or ``None`` if absent.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> prog = ProgramNode(start_position=pos, end_position=pos)
        >>> prog.identification_division is None
        True
    """

    identification_division: ASTNode | None = None
    environment_division: DivisionNode | None = None
    data_division: DataDivisionNode | None = None
    procedure_division: DivisionNode | None = None

    def accept(self, visitor: object) -> object:
        """
        Dispatch to :meth:`~app.parser.ast.visitor.ASTVisitor.visit_program`.

        Args:
            visitor: An :class:`~app.parser.ast.visitor.ASTVisitor`.

        Returns:
            The value returned by ``visitor.visit_program(self)``.
        """
        from app.parser.ast.visitor import ASTVisitor  # avoid circular import

        if isinstance(visitor, ASTVisitor):
            return visitor.visit_program(self)
        raise TypeError(
            f"Visitor must be an ASTVisitor, got {type(visitor).__name__!r}"
        )
