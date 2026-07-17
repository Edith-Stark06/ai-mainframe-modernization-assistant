"""
Procedure Division AST Node.

Purpose:
    Represent the PROCEDURE DIVISION of a COBOL program as an immutable
    AST node that carries the division's ordered paragraphs.

Responsibilities:
    - Hold an ordered tuple of
      :class:`~app.parser.ast.paragraphs.ParagraphNode` instances
      parsed from the PROCEDURE DIVISION.
    - Implement :meth:`accept` for visitor-pattern dispatch.
    - Remain immutable after construction (``frozen=True``).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of paragraphs or statements.
    - SECTION-level grouping (future milestone).
    - DECLARATIVES (future milestone).

Dependencies:
    - :mod:`app.parser.ast.node`       — ``ASTNode`` base class.
    - :mod:`app.parser.ast.paragraphs` — ``ParagraphNode``.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a ProcedureDivisionNode::

        from app.parser.ast.procedure import ProcedureDivisionNode
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        proc = ProcedureDivisionNode(
            start_position=pos,
            end_position=pos,
            paragraphs=(),
        )
        proc.paragraphs  # ()

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.ast.node import ASTNode
from app.parser.ast.paragraphs import ParagraphNode

__all__ = ["ProcedureDivisionNode"]


@dataclass(frozen=True)
class ProcedureDivisionNode(ASTNode):
    """
    Immutable AST node representing the COBOL PROCEDURE DIVISION.

    The PROCEDURE DIVISION contains the executable logic of a COBOL
    program, organised into paragraphs.  This node is the container
    for the ordered sequence of
    :class:`~app.parser.ast.paragraphs.ParagraphNode` instances parsed
    from the division.

    Attributes:
        start_position:
            Source position of the ``PROCEDURE`` keyword.
        end_position:
            Source position of the last token consumed in this division.
        paragraphs:
            Ordered tuple of
            :class:`~app.parser.ast.paragraphs.ParagraphNode` instances.
            Defaults to an empty tuple when no paragraphs are present.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> proc = ProcedureDivisionNode(start_position=pos, end_position=pos)
        >>> proc.paragraphs
        ()
    """

    paragraphs: tuple[ParagraphNode, ...] = field(default_factory=tuple)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_procedure_division(self)`` if available.

        Falls back to a no-op if the visitor does not implement the
        method, preserving backward-compatibility with existing
        :class:`~app.parser.ast.visitor.ASTVisitor` subclasses.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_procedure_division", None)
        if callable(visit):
            return visit(self)
        return None
