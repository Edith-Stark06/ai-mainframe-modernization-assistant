"""
AST Visitor Infrastructure for Semantic Analysis.

Purpose:
    Extend the parser's :class:`~app.parser.ast.visitor.ASTVisitor` base
    class with additional ``visit_*`` hooks for the node types that the
    semantic analyser needs to traverse.

    The visitor pattern allows new analysis passes to be added by
    subclassing :class:`SemanticVisitor` — no AST node class needs to be
    modified.  Every ``visit_*`` method has a default no-op implementation
    so subclasses only override the hooks they care about.

Responsibilities:
    - Provide :class:`SemanticVisitor` — extends
      :class:`~app.parser.ast.visitor.ASTVisitor` with hooks for:
      ``visit_identification_division``,
      ``visit_data_division``,
      ``visit_working_storage_section``,
      ``visit_data_item``,
      ``visit_elementary_item``,
      ``visit_group_item``,
      ``visit_condition_name``,
      ``visit_procedure_division``,
      ``visit_paragraph``.
    - Provide :class:`ProgramTraversalMixin` — a mixin that drives the
      full top-down traversal of a :class:`~app.parser.ast.program.ProgramNode`
      using a :class:`SemanticVisitor`, so concrete visitors do not have
      to implement traversal logic themselves.

Non-responsibilities:
    - Concrete semantic rule logic (belongs in
      :mod:`app.parser.semantic.analyzer` or future specialist visitors).
    - Parsing or token handling.

Dependencies:
    - :mod:`app.parser.ast.visitor` — ``ASTVisitor`` base.
    - :mod:`app.parser.ast.*`       — AST node types (TYPE_CHECKING only).
    - Python standard library only (``abc``).

Examples:
    Implementing a visitor that counts paragraphs::

        from app.parser.semantic.visitors import SemanticVisitor, traverse_program

        class ParagraphCounter(SemanticVisitor):
            def __init__(self) -> None:
                self.count = 0

            def visit_paragraph(self, node):
                self.count += 1

        counter = ParagraphCounter()
        traverse_program(program_node, counter)
        counter.count  # number of paragraphs in the program

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.parser.ast.visitor import ASTVisitor

if TYPE_CHECKING:
    from app.parser.ast.data import DataDivisionNode
    from app.parser.ast.data_items import (
        ConditionNameNode,
        DataItemNode,
        ElementaryItemNode,
        GroupItemNode,
    )
    from app.parser.ast.identification import IdentificationDivisionNode
    from app.parser.ast.paragraphs import ParagraphNode
    from app.parser.ast.procedure import ProcedureDivisionNode
    from app.parser.ast.program import ProgramNode
    from app.parser.ast.working_storage import WorkingStorageSectionNode

__all__ = [
    "SemanticVisitor",
    "traverse_program",
]


# ---------------------------------------------------------------------------
# Extended visitor base
# ---------------------------------------------------------------------------


class SemanticVisitor(ASTVisitor):
    """
    Extended AST visitor base for semantic analysis passes.

    Adds ``visit_*`` hooks for every node type that the semantic analyser
    is expected to inspect.  All methods have default no-op implementations
    so concrete visitors only need to override the hooks they use.

    Subclass this to implement a new semantic rule or analysis pass.

    Attributes:
        None

    Examples:
        >>> class Noop(SemanticVisitor):
        ...     pass
        >>> v = Noop()
        >>> v.visit_paragraph(None) is None
        True
    """

    # -- Identification Division ------------------------------------------

    def visit_identification_division(self, node: IdentificationDivisionNode) -> Any:
        """
        Visit an :class:`~app.parser.ast.identification.IdentificationDivisionNode`.

        Args:
            node: The identification division node.

        Returns:
            ``None`` by default.
        """
        return None

    # -- Data Division & Working-Storage -----------------------------------

    def visit_data_division(self, node: DataDivisionNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.data.DataDivisionNode`.

        Args:
            node: The data division node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_working_storage_section(self, node: WorkingStorageSectionNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.working_storage.WorkingStorageSectionNode`.

        Args:
            node: The working-storage section node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_data_item(self, node: DataItemNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.data_items.DataItemNode`.

        This method is called for generic data items.  For specialised
        dispatch, override :meth:`visit_elementary_item`,
        :meth:`visit_group_item`, or :meth:`visit_condition_name`.

        Args:
            node: The data item node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_elementary_item(self, node: ElementaryItemNode) -> Any:
        """
        Visit an :class:`~app.parser.ast.data_items.ElementaryItemNode`.

        Args:
            node: The elementary item node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_group_item(self, node: GroupItemNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.data_items.GroupItemNode`.

        Args:
            node: The group item node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_condition_name(self, node: ConditionNameNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.data_items.ConditionNameNode`.

        Args:
            node: The condition-name node.

        Returns:
            ``None`` by default.
        """
        return None

    # -- Procedure Division & Paragraphs -----------------------------------

    def visit_procedure_division(self, node: ProcedureDivisionNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.procedure.ProcedureDivisionNode`.

        Args:
            node: The procedure division node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_paragraph(self, node: ParagraphNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.paragraphs.ParagraphNode`.

        Args:
            node: The paragraph node.

        Returns:
            ``None`` by default.
        """
        return None


# ---------------------------------------------------------------------------
# Traversal driver
# ---------------------------------------------------------------------------


def traverse_program(program: ProgramNode, visitor: SemanticVisitor) -> None:
    """
    Drive a full top-down traversal of *program* using *visitor*.

    This function implements the default traversal strategy used by
    :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`.  It visits
    each division in declaration order, then visits each section and item
    within that division.

    The traversal order is::

        ProgramNode
        └── IdentificationDivisionNode
        └── DataDivisionNode
            └── WorkingStorageSectionNode
                └── DataItemNode   (ElementaryItemNode | GroupItemNode | ConditionNameNode)
        └── ProcedureDivisionNode
            └── ParagraphNode (×N)

    Args:
        program:
            The :class:`~app.parser.ast.program.ProgramNode` to traverse.
        visitor:
            The :class:`SemanticVisitor` instance to dispatch node visits to.

    Examples:
        >>> from app.parser.semantic.visitors import SemanticVisitor, traverse_program
        >>> class Counter(SemanticVisitor):
        ...     def __init__(self): self.n = 0
        ...     def visit_paragraph(self, node): self.n += 1
    """
    # --- top-level program -------------------------------------------------
    visitor.visit_program(program)

    # --- identification division ------------------------------------------
    ident = program.identification_division
    if ident is not None:
        ident.accept(visitor)

    # --- data division ----------------------------------------------------
    data_div = program.data_division
    if data_div is not None:
        visitor.visit_data_division(data_div)
        ws = data_div.working_storage
        if ws is not None:
            visitor.visit_working_storage_section(ws)
            for item in ws.items:
                item.accept(visitor)

    # --- procedure division -----------------------------------------------
    proc_div = program.procedure_division
    if proc_div is not None:
        visitor.visit_procedure_division(proc_div)
        for para in proc_div.paragraphs:
            para.accept(visitor)
