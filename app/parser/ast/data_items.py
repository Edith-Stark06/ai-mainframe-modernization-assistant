"""
Data Division Item AST Nodes.

Purpose:
    Define the immutable AST nodes that represent individual data items
    (records and elementary items) that may appear inside the COBOL DATA
    DIVISION.

    Each node carries the structural information captured during parsing:
    level number, data name, PICTURE clause, and VALUE clause.  Nodes
    are kept deliberately thin — semantic analysis is a separate concern.

Responsibilities:
    - Provide :class:`DataItemNode` — the base for any data-division entry.
    - Provide :class:`ElementaryItemNode` — level 01/05/77 items with a PIC
      clause.
    - Provide :class:`GroupItemNode` — level 01/05 group records (no PIC).
    - Provide :class:`ConditionNameNode` — level 88 condition-name entries.
    - Remain immutable after construction (``frozen=True`` dataclasses).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation (COMP, INDEXED BY, etc.).
    - Visitor dispatch (handled by the ASTVisitor extension point).

Dependencies:
    - :mod:`app.parser.ast.node` — ``ASTNode`` base class.
    - Python standard library only (``dataclasses``).

Examples:
    Creating an elementary data item node::

        from app.parser.ast.data_items import ElementaryItemNode
        from app.parser.lexer.position import Position

        pos = Position(line=5, column=4, offset=80, filename="prog.cbl")
        node = ElementaryItemNode(
            start_position=pos,
            end_position=pos,
            level=5,
            name="CUSTOMER-ID",
            picture="9(5)",
        )
        node.level   # 5
        node.name    # "CUSTOMER-ID"
        node.picture # "9(5)"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.ast.node import ASTNode

__all__ = [
    "ConditionNameNode",
    "DataItemNode",
    "ElementaryItemNode",
    "GroupItemNode",
]


@dataclass(frozen=True)
class DataItemNode(ASTNode):
    """
    Abstract base for all DATA DIVISION item nodes.

    Every concrete data-item node (elementary, group, condition-name)
    inherits from this class and gains a ``level`` (integer level number)
    and a ``name`` (data-name string).

    Attributes:
        start_position:
            Source position of the item's level number token.
        end_position:
            Source position of the last token consumed for this item.
        level:
            The COBOL level number (e.g. 1, 5, 77, 88).
        name:
            The data-name as it appears in the source (uppercased).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> # DataItemNode is abstract — instantiate a concrete subclass.
    """

    level: int
    name: str

    def accept(self, visitor: object) -> object:
        """
        Dispatch to the appropriate visitor method.

        Concrete subclasses override this to call the specific visitor
        method that matches their node type.

        Args:
            visitor: Any visitor object.

        Returns:
            Whatever the visitor method returns, or ``None``.
        """
        visit = getattr(visitor, "visit_data_item", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class ElementaryItemNode(DataItemNode):
    """
    Immutable AST node for an elementary COBOL data item.

    An elementary item has a PICTURE clause that defines its data type
    and size.  It may also carry an optional VALUE clause.  Level
    numbers 01–49 and 77 may be elementary items.

    COBOL syntax example::

        05 CUSTOMER-ID     PIC 9(5).
        77 WS-COUNT        PIC 9(4).

    Attributes:
        level:
            The COBOL level number (1–49, 77).
        name:
            The data-name string (uppercased).
        picture:
            The picture string (e.g. ``"9(5)"``, ``"X(30)"``).
        value:
            The optional VALUE clause literal (e.g. ``"0"``), or
            ``None`` if absent.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=5, column=4, offset=80, filename="x.cbl")
        >>> node = ElementaryItemNode(
        ...     start_position=pos, end_position=pos,
        ...     level=5, name="CUST-ID", picture="9(5)",
        ... )
        >>> node.picture
        '9(5)'
    """

    picture: str
    value: str | None = None

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_elementary_item(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_elementary_item", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class GroupItemNode(DataItemNode):
    """
    Immutable AST node for a COBOL group data item.

    A group item has no PICTURE clause of its own; its subordinate items
    define the actual storage layout.  Group items may appear at level
    numbers 01–49 (but never 77 or 88).

    COBOL syntax example::

        01 CUSTOMER-REC.
           05 CUSTOMER-ID   PIC 9(5).
           05 CUSTOMER-NAME PIC X(30).

    Attributes:
        level:
            The COBOL level number (typically 1 or 5).
        name:
            The group-name string (uppercased).
        children:
            Ordered tuple of subordinate :class:`DataItemNode` instances.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=3, column=1, offset=40, filename="x.cbl")
        >>> node = GroupItemNode(
        ...     start_position=pos, end_position=pos,
        ...     level=1, name="CUSTOMER-REC", children=(),
        ... )
        >>> node.children
        ()
    """

    children: tuple[DataItemNode, ...] = field(default_factory=tuple)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_group_item(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_group_item", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class ConditionNameNode(DataItemNode):
    """
    Immutable AST node for a COBOL 88-level condition-name entry.

    A condition-name associates a Boolean condition with a data item by
    specifying the VALUE (or VALUES) that make the condition true.
    Level 88 items always appear immediately subordinate to a data item.

    COBOL syntax example::

        88 END-OF-FILE   VALUE 'Y'.

    Attributes:
        level:
            Always ``88`` for condition-name entries.
        name:
            The condition-name string (uppercased).
        value:
            The VALUE literal string (e.g. ``"'Y'"``), or ``None`` if
            the VALUE clause was absent (partial parse).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=10, column=4, offset=200, filename="x.cbl")
        >>> node = ConditionNameNode(
        ...     start_position=pos, end_position=pos,
        ...     level=88, name="END-OF-FILE", value="'Y'",
        ... )
        >>> node.value
        "'Y'"
    """

    value: str | None = None

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_condition_name(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_condition_name", None)
        if callable(visit):
            return visit(self)
        return None
