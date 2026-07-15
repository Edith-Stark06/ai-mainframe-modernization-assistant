"""
Identification Division Clause AST Nodes.

Purpose:
    Define the immutable AST nodes that represent each clause that may
    appear inside the COBOL IDENTIFICATION DIVISION.

    Each clause carries a ``value`` field holding the raw text of the
    clause's argument and inherits ``start_position`` / ``end_position``
    from :class:`~app.parser.ast.node.ASTNode`.

Responsibilities:
    - Provide :class:`ProgramIdClauseNode`    — PROGRAM-ID clause.
    - Provide :class:`AuthorClauseNode`        — AUTHOR clause.
    - Provide :class:`InstallationClauseNode`  — INSTALLATION clause.
    - Provide :class:`DateWrittenClauseNode`   — DATE-WRITTEN clause.
    - Provide :class:`DateCompiledClauseNode`  — DATE-COMPILED clause.
    - Provide :class:`SecurityClauseNode`      — SECURITY clause.
    - Remain immutable after construction (``frozen=True`` dataclasses).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of clause values.
    - Visitor dispatch (handled by the ASTVisitor extension point).

Dependencies:
    - :mod:`app.parser.ast.node` — ``ASTNode`` base class.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a PROGRAM-ID clause node::

        from app.parser.ast.clauses import ProgramIdClauseNode
        from app.parser.lexer.position import Position

        pos = Position(line=2, column=12, offset=40, filename="prog.cbl")
        node = ProgramIdClauseNode(
            start_position=pos,
            end_position=pos,
            value="PAYROLL",
        )
        node.value  # "PAYROLL"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.parser.ast.node import ASTNode

__all__ = [
    "AuthorClauseNode",
    "DateCompiledClauseNode",
    "DateWrittenClauseNode",
    "InstallationClauseNode",
    "ProgramIdClauseNode",
    "SecurityClauseNode",
]


@dataclass(frozen=True)
class ProgramIdClauseNode(ASTNode):
    """
    Immutable AST node for the PROGRAM-ID clause.

    COBOL syntax::

        PROGRAM-ID. <program-name> .

    Attributes:
        value:
            The program name as it appears in the source (e.g.
            ``\"PAYROLL\"``).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=2, column=1, offset=20, filename="x.cbl")
        >>> node = ProgramIdClauseNode(
        ...     start_position=pos, end_position=pos, value="PAYROLL"
        ... )
        >>> node.value
        'PAYROLL'
    """

    value: str

    def accept(self, visitor: object) -> object:
        """Dispatch to ``visitor.visit_program_id_clause(self)`` if available."""
        visit = getattr(visitor, "visit_program_id_clause", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class AuthorClauseNode(ASTNode):
    """
    Immutable AST node for the AUTHOR clause.

    COBOL syntax::

        AUTHOR. <comment-entry> .

    Attributes:
        value: The author text as it appears in the source.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=3, column=1, offset=40, filename="x.cbl")
        >>> node = AuthorClauseNode(
        ...     start_position=pos, end_position=pos, value="EDITH STARK"
        ... )
        >>> node.value
        'EDITH STARK'
    """

    value: str

    def accept(self, visitor: object) -> object:
        """Dispatch to ``visitor.visit_author_clause(self)`` if available."""
        visit = getattr(visitor, "visit_author_clause", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class InstallationClauseNode(ASTNode):
    """
    Immutable AST node for the INSTALLATION clause.

    COBOL syntax::

        INSTALLATION. <comment-entry> .

    Attributes:
        value: The installation text as it appears in the source.
    """

    value: str

    def accept(self, visitor: object) -> object:
        """Dispatch to ``visitor.visit_installation_clause(self)`` if available."""
        visit = getattr(visitor, "visit_installation_clause", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class DateWrittenClauseNode(ASTNode):
    """
    Immutable AST node for the DATE-WRITTEN clause.

    COBOL syntax::

        DATE-WRITTEN. <comment-entry> .

    Attributes:
        value: The date-written text as it appears in the source.
    """

    value: str

    def accept(self, visitor: object) -> object:
        """Dispatch to ``visitor.visit_date_written_clause(self)`` if available."""
        visit = getattr(visitor, "visit_date_written_clause", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class DateCompiledClauseNode(ASTNode):
    """
    Immutable AST node for the DATE-COMPILED clause.

    COBOL syntax::

        DATE-COMPILED. <comment-entry> .

    Attributes:
        value: The date-compiled text as it appears in the source.
    """

    value: str

    def accept(self, visitor: object) -> object:
        """Dispatch to ``visitor.visit_date_compiled_clause(self)`` if available."""
        visit = getattr(visitor, "visit_date_compiled_clause", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class SecurityClauseNode(ASTNode):
    """
    Immutable AST node for the SECURITY clause.

    COBOL syntax::

        SECURITY. <comment-entry> .

    Attributes:
        value: The security text as it appears in the source.
    """

    value: str

    def accept(self, visitor: object) -> object:
        """Dispatch to ``visitor.visit_security_clause(self)`` if available."""
        visit = getattr(visitor, "visit_security_clause", None)
        if callable(visit):
            return visit(self)
        return None
