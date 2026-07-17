"""
Paragraph AST Node.

Purpose:
    Represent a COBOL paragraph as an immutable AST node.  A paragraph
    is a named block of executable statements within the PROCEDURE
    DIVISION.

Responsibilities:
    - Hold the paragraph name (label).
    - Hold an ordered tuple of
      :class:`~app.parser.ast.statements.StatementNode` instances that
      form the paragraph body.
    - Implement :meth:`accept` for visitor-pattern dispatch.
    - Remain immutable after construction (``frozen=True``).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of paragraph contents.
    - SECTION-level grouping of paragraphs.

Dependencies:
    - :mod:`app.parser.ast.node`       — ``ASTNode`` base class.
    - :mod:`app.parser.ast.statements` — ``StatementNode``.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a ParagraphNode::

        from app.parser.ast.paragraphs import ParagraphNode
        from app.parser.lexer.position import Position

        pos = Position(line=5, column=1, offset=80, filename="prog.cbl")
        para = ParagraphNode(
            start_position=pos,
            end_position=pos,
            name="MAIN-PARA",
            statements=(),
        )
        para.name        # 'MAIN-PARA'
        para.statements  # ()

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.ast.node import ASTNode
from app.parser.ast.statements import StatementNode

__all__ = ["ParagraphNode"]


@dataclass(frozen=True)
class ParagraphNode(ASTNode):
    """
    Immutable AST node representing a COBOL paragraph.

    A paragraph begins with a paragraph label followed by a period and
    contains zero or more executable statements.  Paragraph names are
    user-defined identifiers and are stored in uppercased form.

    COBOL syntax example::

        MAIN-PARA.
            DISPLAY "HELLO".
            MOVE 1 TO WS-COUNT.
            STOP RUN.

    Attributes:
        start_position:
            Source position of the paragraph's label token.
        end_position:
            Source position of the last token consumed for this paragraph.
        name:
            The paragraph label string (uppercased).
        statements:
            Ordered tuple of :class:`~app.parser.ast.statements.StatementNode`
            instances that form the paragraph body.  Defaults to an
            empty tuple.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=5, column=1, offset=80, filename="x.cbl")
        >>> para = ParagraphNode(
        ...     start_position=pos, end_position=pos, name="MAIN-PARA",
        ... )
        >>> para.name
        'MAIN-PARA'
        >>> para.statements
        ()
    """

    name: str
    statements: tuple[StatementNode, ...] = field(default_factory=tuple)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_paragraph(self)`` if available.

        Falls back to a no-op if the visitor does not implement the
        method, preserving backward-compatibility with existing
        :class:`~app.parser.ast.visitor.ASTVisitor` subclasses.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_paragraph", None)
        if callable(visit):
            return visit(self)
        return None
