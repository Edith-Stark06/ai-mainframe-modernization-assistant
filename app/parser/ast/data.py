"""
Data Division AST Node.

Purpose:
    Represent the DATA DIVISION of a COBOL program as an immutable AST
    node that carries references to the division's parsed sections.

Responsibilities:
    - Hold an optional
      :class:`~app.parser.ast.working_storage.WorkingStorageSectionNode`
      for the WORKING-STORAGE SECTION.
    - Implement :meth:`accept` for visitor-pattern dispatch.
    - Remain immutable after construction (``frozen=True``).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation of section or item contents.
    - Unimplemented sections (FILE, LINKAGE, LOCAL-STORAGE, SCREEN, REPORT).

Dependencies:
    - :mod:`app.parser.ast.node`             — ``ASTNode`` base class.
    - :mod:`app.parser.ast.working_storage`  — ``WorkingStorageSectionNode``.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a DataDivisionNode::

        from app.parser.ast.data import DataDivisionNode
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        data_div = DataDivisionNode(
            start_position=pos,
            end_position=pos,
        )
        data_div.working_storage is None  # True

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.parser.ast.node import ASTNode
from app.parser.ast.working_storage import WorkingStorageSectionNode

__all__ = ["DataDivisionNode"]


@dataclass(frozen=True)
class DataDivisionNode(ASTNode):
    """
    Immutable AST node representing the COBOL DATA DIVISION.

    The DATA DIVISION is the container for all data-definition sections.
    In this milestone only the WORKING-STORAGE SECTION is supported;
    future tasks will add FILE, LINKAGE, LOCAL-STORAGE, SCREEN, and
    REPORT sections.

    Attributes:
        start_position:
            Source position of the ``DATA`` keyword.
        end_position:
            Source position of the last token consumed in this division.
        working_storage:
            The WORKING-STORAGE SECTION node, or ``None`` if absent.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> node = DataDivisionNode(start_position=pos, end_position=pos)
        >>> node.working_storage is None
        True
    """

    working_storage: WorkingStorageSectionNode | None = None

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_data_division(self)`` if available.

        Falls back to a no-op if the visitor does not implement the method,
        preserving backward-compatibility with existing
        :class:`~app.parser.ast.visitor.ASTVisitor` subclasses.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_data_division", None)
        if callable(visit):
            return visit(self)
        return None
