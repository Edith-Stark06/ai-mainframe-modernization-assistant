"""
Working-Storage Section AST Node.

Purpose:
    Represent the WORKING-STORAGE SECTION of the COBOL DATA DIVISION as
    an immutable AST node that carries the section's parsed data items.

Responsibilities:
    - Hold an ordered tuple of :class:`~app.parser.ast.data_items.DataItemNode`
      instances that were declared in the WORKING-STORAGE SECTION.
    - Implement :meth:`accept` for visitor-pattern dispatch.
    - Remain immutable after construction (``frozen=True``).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of data items.
    - Other DATA DIVISION sections (FILE, LINKAGE, etc.).

Dependencies:
    - :mod:`app.parser.ast.node`       — ``ASTNode`` base class.
    - :mod:`app.parser.ast.data_items` — ``DataItemNode``.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a WorkingStorageSectionNode::

        from app.parser.ast.working_storage import WorkingStorageSectionNode
        from app.parser.lexer.position import Position

        pos = Position(line=3, column=1, offset=40, filename="prog.cbl")
        ws = WorkingStorageSectionNode(
            start_position=pos,
            end_position=pos,
            items=(),
        )
        ws.items  # ()

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.ast.data_items import DataItemNode
from app.parser.ast.node import ASTNode

__all__ = ["WorkingStorageSectionNode"]


@dataclass(frozen=True)
class WorkingStorageSectionNode(ASTNode):
    """
    Immutable AST node representing the COBOL WORKING-STORAGE SECTION.

    The WORKING-STORAGE SECTION holds data items that persist for the
    duration of the program's execution.  This node is a container for
    the top-level :class:`~app.parser.ast.data_items.DataItemNode`
    instances declared in that section.

    Attributes:
        start_position:
            Source position of the ``WORKING-STORAGE`` keyword.
        end_position:
            Source position of the last token consumed in this section.
        items:
            Ordered tuple of top-level
            :class:`~app.parser.ast.data_items.DataItemNode` instances.
            Defaults to an empty tuple.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=3, column=1, offset=40, filename="x.cbl")
        >>> ws = WorkingStorageSectionNode(start_position=pos, end_position=pos)
        >>> ws.items
        ()
    """

    items: tuple[DataItemNode, ...] = field(default_factory=tuple)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_working_storage_section(self)`` if available.

        Falls back to a no-op if the visitor does not implement the method,
        preserving backward-compatibility with existing
        :class:`~app.parser.ast.visitor.ASTVisitor` subclasses.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_working_storage_section", None)
        if callable(visit):
            return visit(self)
        return None
