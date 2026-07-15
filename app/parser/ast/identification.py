"""
Identification Division AST Node.

Purpose:
    Represent the IDENTIFICATION DIVISION of a COBOL program as an
    immutable AST node that carries the division's parsed clauses.

Responsibilities:
    - Hold an optional :class:`~app.parser.ast.clauses.ProgramIdClauseNode`
      (mandatory by grammar, optional in the AST for resilience).
    - Hold optional clause nodes for AUTHOR, INSTALLATION, DATE-WRITTEN,
      DATE-COMPILED, and SECURITY.
    - Implement :meth:`accept` for visitor-pattern dispatch.
    - Remain immutable after construction (``frozen=True``).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of division contents.

Dependencies:
    - :mod:`app.parser.ast.node`    — ``ASTNode`` base class.
    - :mod:`app.parser.ast.clauses` — clause node types.
    - Python standard library only (``dataclasses``).

Examples:
    Creating an IdentificationDivisionNode::

        from app.parser.ast.identification import IdentificationDivisionNode
        from app.parser.ast.clauses import ProgramIdClauseNode
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        pid = ProgramIdClauseNode(
            start_position=pos, end_position=pos, value="PAYROLL"
        )
        ident = IdentificationDivisionNode(
            start_position=pos,
            end_position=pos,
            program_id=pid,
        )
        ident.program_id.value  # "PAYROLL"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.parser.ast.clauses import (
    AuthorClauseNode,
    DateCompiledClauseNode,
    DateWrittenClauseNode,
    InstallationClauseNode,
    ProgramIdClauseNode,
    SecurityClauseNode,
)
from app.parser.ast.node import ASTNode

__all__ = ["IdentificationDivisionNode"]


@dataclass(frozen=True)
class IdentificationDivisionNode(ASTNode):
    """
    Immutable AST node representing the COBOL IDENTIFICATION DIVISION.

    This node is the top-level container for all clauses that may appear
    in the IDENTIFICATION DIVISION.  The PROGRAM-ID clause is
    semantically mandatory, but the AST represents it as optional
    (``None``) so that the parser can produce a partial tree even when
    the source is syntactically incomplete.

    Attributes:
        start_position:
            Source position of the ``IDENTIFICATION`` keyword.
        end_position:
            Source position of the last token consumed in this division.
        program_id:
            The PROGRAM-ID clause node, or ``None`` if absent.
        author:
            The AUTHOR clause node, or ``None`` if absent.
        installation:
            The INSTALLATION clause node, or ``None`` if absent.
        date_written:
            The DATE-WRITTEN clause node, or ``None`` if absent.
        date_compiled:
            The DATE-COMPILED clause node, or ``None`` if absent.
        security:
            The SECURITY clause node, or ``None`` if absent.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> node = IdentificationDivisionNode(start_position=pos, end_position=pos)
        >>> node.program_id is None
        True
    """

    program_id: ProgramIdClauseNode | None = None
    author: AuthorClauseNode | None = None
    installation: InstallationClauseNode | None = None
    date_written: DateWrittenClauseNode | None = None
    date_compiled: DateCompiledClauseNode | None = None
    security: SecurityClauseNode | None = None

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_identification_division(self)``.

        Falls back to a no-op if the visitor does not implement the
        method, preserving backward-compatibility with existing
        :class:`~app.parser.ast.visitor.ASTVisitor` subclasses.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_identification_division", None)
        if callable(visit):
            return visit(self)
        return None
