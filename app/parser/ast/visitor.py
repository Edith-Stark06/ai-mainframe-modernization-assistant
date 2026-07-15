"""
AST Visitor Base Class.

Purpose:
    Define the Visitor interface for traversing the COBOL Abstract
    Syntax Tree.

    The Visitor pattern decouples tree structure from tree operations.
    New analysis passes are implemented by subclassing
    :class:`ASTVisitor` and overriding the relevant ``visit_*`` methods,
    without modifying any AST node class.

Responsibilities:
    - Provide ``visit_program()`` for visiting :class:`~app.parser.ast.program.ProgramNode`.
    - Provide ``visit_division()`` for visiting :class:`~app.parser.ast.division.DivisionNode`.
    - Supply no-op default implementations so that subclasses only need
      to override the methods they care about.
    - Be extensible: future tasks will add ``visit_section()``,
      ``visit_paragraph()``, ``visit_statement()``, etc.

Non-responsibilities:
    - Parsing, lexing, or position tracking.
    - Concrete analysis logic (belongs in subclasses).

Dependencies:
    - :mod:`app.parser.ast.program`   — ``ProgramNode``.
    - :mod:`app.parser.ast.division`  — ``DivisionNode``.
    - Python standard library only (``abc``).

Examples:
    Implementing a visitor that collects division names::

        from app.parser.ast.visitor import ASTVisitor
        from app.parser.ast.program import ProgramNode
        from app.parser.ast.division import DivisionNode

        class DivisionCollector(ASTVisitor):
            def __init__(self) -> None:
                self.names: list[str] = []

            def visit_division(self, node: DivisionNode) -> None:
                self.names.append(node.name)

        collector = DivisionCollector()
        program.accept(collector)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.parser.ast.division import DivisionNode
    from app.parser.ast.program import ProgramNode

__all__ = ["ASTVisitor"]


class ASTVisitor(ABC):
    """
    Base visitor for the COBOL Abstract Syntax Tree.

    Subclass this to implement an analysis pass over the AST.  Override
    the ``visit_*`` methods corresponding to the node types you wish to
    process; unoverridden methods are no-ops that return ``None``.

    All node classes call the appropriate ``visit_*`` method via their
    :meth:`~app.parser.ast.node.ASTNode.accept` implementations, so the
    standard usage is::

        visitor = MyConcreteVisitor()
        program_node.accept(visitor)

    Examples:
        >>> class Noop(ASTVisitor):
        ...     pass
        >>> v = Noop()
        >>> v.visit_program(None)  # no-op, returns None
    """

    def visit_program(self, node: ProgramNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.program.ProgramNode`.

        The default implementation is a no-op.  Override in subclasses
        to inspect or transform the program node.

        Args:
            node: The program node being visited.

        Returns:
            ``None`` by default; subclasses may return any value.
        """
        return None

    def visit_division(self, node: DivisionNode) -> Any:
        """
        Visit a :class:`~app.parser.ast.division.DivisionNode`.

        The default implementation is a no-op.  Override in subclasses
        to inspect or transform a division node.

        Args:
            node: The division node being visited.

        Returns:
            ``None`` by default; subclasses may return any value.
        """
        return None
