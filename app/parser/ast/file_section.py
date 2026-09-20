"""
File Section AST Nodes.

Purpose:
    Represent the COBOL DATA DIVISION's FILE SECTION -- one ``FD``
    (File Description) entry per file, each carrying the data items of
    its record layout -- as immutable AST nodes.

Responsibilities:
    - Hold an ordered tuple of :class:`FileDescriptionNode` instances
      declared in the FILE SECTION (:class:`FileSectionNode`).
    - Hold one ``FD``'s file-name and the ordered tuple of
      :class:`~app.parser.ast.data_items.DataItemNode` instances that
      describe its record (:class:`FileDescriptionNode`) -- the exact
      same node types (``ElementaryItemNode``/``GroupItemNode``/
      ``ConditionNameNode``) a WORKING-STORAGE ``01`` record already
      uses, so every existing consumer of those types (symbol
      collection, Java field construction, condition-name lookup) needs
      no special-casing to also see a FILE SECTION record's fields.
    - Implement :meth:`accept` for visitor-pattern dispatch on both
      node types.
    - Remain immutable after construction (``frozen=True``).

Non-responsibilities:
    - Parsing or lexical analysis.
    - FD clauses other than the file-name (``LABEL RECORDS``, ``BLOCK
      CONTAINS``, ``RECORD CONTAINS``, ...) -- none appear in the
      corpus; the parser tolerates and skips them without modelling
      their content (see ``DataDivisionParser._parse_file_description``).
    - Semantic validation of record contents.

Dependencies:
    - :mod:`app.parser.ast.node`       -- ``ASTNode`` base class.
    - :mod:`app.parser.ast.data_items` -- ``DataItemNode``.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a FileSectionNode::

        from app.parser.ast.file_section import FileDescriptionNode, FileSectionNode
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        fd = FileDescriptionNode(
            start_position=pos, end_position=pos, name="ACCT-IN-FILE", items=(),
        )
        fs = FileSectionNode(start_position=pos, end_position=pos, records=(fd,))
        fs.records[0].name  # "ACCT-IN-FILE"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.ast.data_items import DataItemNode
from app.parser.ast.node import ASTNode

__all__ = ["FileDescriptionNode", "FileSectionNode"]


@dataclass(frozen=True)
class FileDescriptionNode(ASTNode):
    """
    Immutable AST node representing one FILE SECTION ``FD`` entry.

    Attributes:
        start_position:
            Source position of the ``FD`` keyword.
        end_position:
            Source position of the last token consumed for this entry
            (the end of its record's data items).
        name:
            The file-name declared on the ``FD`` line (e.g.
            ``"ACCT-IN-FILE"``), uppercased by the parser.
        items:
            Ordered tuple of the record's top-level
            :class:`~app.parser.ast.data_items.DataItemNode` instances
            -- the same node types, and the same nesting convention
            (``children`` on a group item), a WORKING-STORAGE ``01``
            record already uses. A real ``FD`` describes exactly one
            record; this parser does not model multiple ``01``s under
            one ``FD`` (not present in the corpus).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=12, column=8, offset=200, filename="x.cbl")
        >>> fd = FileDescriptionNode(
        ...     start_position=pos, end_position=pos, name="ACCT-IN-FILE",
        ... )
        >>> fd.items
        ()
    """

    name: str = ""
    items: tuple[DataItemNode, ...] = field(default_factory=tuple)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_file_description(self)`` if available.

        Falls back to a no-op if the visitor does not implement the
        method, preserving backward-compatibility with existing
        :class:`~app.parser.ast.visitor.ASTVisitor` subclasses.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_file_description", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class FileSectionNode(ASTNode):
    """
    Immutable AST node representing the COBOL FILE SECTION.

    The FILE SECTION declares the record layout of every file named in
    the ENVIRONMENT DIVISION's ``FILE-CONTROL`` paragraph, one ``FD``
    entry per file. This node is a container for the section's ordered
    :class:`FileDescriptionNode` entries.

    Attributes:
        start_position:
            Source position of the ``FILE`` keyword.
        end_position:
            Source position of the last token consumed in this section.
        records:
            Ordered tuple of :class:`FileDescriptionNode` instances.
            Defaults to an empty tuple.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=11, column=1, offset=180, filename="x.cbl")
        >>> fs = FileSectionNode(start_position=pos, end_position=pos)
        >>> fs.records
        ()
    """

    records: tuple[FileDescriptionNode, ...] = field(default_factory=tuple)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_file_section(self)`` if available.

        Falls back to a no-op if the visitor does not implement the
        method, preserving backward-compatibility with existing
        :class:`~app.parser.ast.visitor.ASTVisitor` subclasses.

        Args:
            visitor: Any visitor object.

        Returns:
            The value returned by the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_file_section", None)
        if callable(visit):
            return visit(self)
        return None
