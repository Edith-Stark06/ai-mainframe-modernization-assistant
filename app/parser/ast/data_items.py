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
        occurs:
            The declared cardinality of an ``OCCURS n [TIMES]`` clause
            (task #stage32), or ``None`` if the item has none. Both
            ``OCCURS 5`` and ``OCCURS 5 TIMES`` produce the same value —
            ``TIMES`` is consumed as optional syntax, never required.
            ``OCCURS DEPENDING ON``, ``INDEXED BY``, and any other
            qualifier beyond the bare count remain unrepresented and out
            of scope; see
            :meth:`~app.parser.syntax.data_parser.DataDivisionParser._parse_occurs_clause`.
        redefines:
            The base item's data-name from a ``REDEFINES base-name``
            clause (task #stage39), uppercased, or ``None`` if the item
            has none. An item whose own name is redefined by a *later*
            sibling is unaffected — this field only ever names what
            *this* item itself redefines, never the reverse. See
            :meth:`~app.parser.syntax.data_parser.DataDivisionParser._parse_elementary_or_group`
            for exactly how the clause is recognised, and
            :func:`~app.backend.java.generator._resolve_redefines_values`
            for how a redefining *group*'s elementary children derive
            their initial value from the base item's own ``VALUE``
            literal (the one evidenced corpus shape; an elementary item
            redefining another elementary item is captured here but not
            further resolved — unevidenced).
        usage:
            The uppercased operand of a ``USAGE [IS] usage-word`` clause,
            or of a bare ``usage-word`` (no leading ``USAGE`` keyword —
            both are valid COBOL, and the real training corpus uses the
            bare form exclusively), e.g. ``"COMP-3"``, ``"COMP"``,
            ``"BINARY"``, ``"PACKED-DECIMAL"`` (task #stage41), or
            ``None`` if the item has none (equivalent to ``DISPLAY``).
            Recorded exactly as written -- alias normalisation
            (``BINARY`` -> ``COMP``, ``PACKED-DECIMAL`` -> ``COMP-3``,
            ...) happens downstream in
            :meth:`~app.parser.semantic.type_builder.TypeBuilder.usage_from_string`,
            not here. See
            :meth:`~app.parser.syntax.data_parser.DataDivisionParser._parse_usage_clause`
            for exactly how the clause is recognised. This affects only
            the resolved :class:`~app.parser.semantic.types.UsageType`
            attached during semantic analysis, never the generated Java
            (which derives its field type from ``picture`` alone) -- a
            purely representational fix, not a behavior change.

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
    occurs: int | None = field(default=None, metadata={"omit_if_empty": True})
    redefines: str | None = field(default=None, metadata={"omit_if_empty": True})
    usage: str | None = field(default=None, metadata={"omit_if_empty": True})

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
        occurs:
            The declared cardinality of an ``OCCURS n [TIMES]`` clause on
            the *group itself* (task #stage32) — e.g. a repeating record,
            ``05 WS-ENTRY OCCURS 5 TIMES.`` with its own ``children`` —
            or ``None`` if the group does not repeat. See
            :attr:`ElementaryItemNode.occurs` for the exact grammar
            accepted and what remains unrepresented.
        redefines:
            The base item's data-name from a ``REDEFINES base-name``
            clause (task #stage39), uppercased, or ``None`` if the item
            has none — see :attr:`ElementaryItemNode.redefines` for the
            full explanation; a redefining *group* (this corpus's one
            evidenced shape, e.g. ``05 AUTO-PAYLOAD REDEFINES
            POLICY-RAW-PAYLOAD.``) is the form
            :func:`~app.backend.java.generator._resolve_redefines_values`
            actually derives child values for.
        usage:
            A ``USAGE`` clause on the group itself (task #stage41), or
            ``None`` if it has none — see :attr:`ElementaryItemNode.usage`
            for the full explanation. Unevidenced in the real training
            corpus (every ``COMP``/``COMP-3`` occurrence there is on an
            elementary item); captured here for grammatical symmetry with
            :attr:`occurs`/:attr:`redefines`, but no downstream consumer
            (semantic analysis, Java generation) currently reads a
            group's own ``usage`` -- COBOL's group-level USAGE
            inheritance to elementary children is not implemented.

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
    occurs: int | None = field(default=None, metadata={"omit_if_empty": True})
    redefines: str | None = field(default=None, metadata={"omit_if_empty": True})
    usage: str | None = field(default=None, metadata={"omit_if_empty": True})

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

    COBOL syntax examples::

        88 END-OF-FILE   VALUE 'Y'.
        88 TX-VALID-KIND VALUES 'D' 'W' 'T' 'F'.

    Attributes:
        level:
            Always ``88`` for condition-name entries.
        name:
            The condition-name string (uppercased).
        value:
            The single VALUE literal string (e.g. ``"'Y'"``), for backward
            compatibility with every existing reader of this field. Set for
            a singular ``VALUE literal`` clause; ``None`` when the clause
            was absent *or* when it was the plural ``VALUES`` form (which
            has no single canonical value — see :attr:`values` instead).
        values:
            The complete, ordered tuple of VALUE/VALUES literal strings.
            One element for a singular ``VALUE literal`` clause (mirroring
            :attr:`value`), two or more for a plural ``VALUES literal
            literal ...`` clause, and empty when no clause was present.
            This is the authoritative field — a consumer that needs every
            literal a condition-name can take (not just "the" one) should
            read this rather than :attr:`value`.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=10, column=4, offset=200, filename="x.cbl")
        >>> node = ConditionNameNode(
        ...     start_position=pos, end_position=pos,
        ...     level=88, name="END-OF-FILE", value="'Y'", values=("'Y'",),
        ... )
        >>> node.value
        "'Y'"
        >>> multi = ConditionNameNode(
        ...     start_position=pos, end_position=pos,
        ...     level=88, name="TX-VALID-KIND",
        ...     values=("'D'", "'W'", "'T'", "'F'"),
        ... )
        >>> multi.value is None
        True
        >>> multi.values
        ("'D'", "'W'", "'T'", "'F'")
    """

    value: str | None = None
    values: tuple[str, ...] = ()

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
