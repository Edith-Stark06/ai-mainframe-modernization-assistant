"""
Abstract Syntax Tree Base Node.

Purpose:
    Provide the common base class for every node in the COBOL Abstract
    Syntax Tree.  All concrete AST nodes inherit from :class:`ASTNode`.

Responsibilities:
    - Carry source position information (start and end) for every node.
    - Guarantee immutability so that AST nodes may be shared across
      analysis passes without defensive copying.
    - Supply a clean ``accept()`` hook for visitor-pattern dispatch.

Non-responsibilities:
    - Parsing, scanning, or lexical analysis.
    - Semantic analysis or type checking.
    - Code generation.

Dependencies:
    - :mod:`app.parser.lexer.position` — ``Position`` value type.
    - Python standard library only (``dataclasses``, ``abc``).

Examples:
    Sub-classing ASTNode::

        from app.parser.ast.node import ASTNode
        from app.parser.lexer.position import Position

        @dataclass(frozen=True)
        class MyNode(ASTNode):
            name: str

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.parser.lexer.position import Position

__all__ = ["ASTNode"]


@dataclass(frozen=True)
class ASTNode(ABC):
    """
    Immutable base class for all COBOL Abstract Syntax Tree nodes.

    Every concrete AST node must inherit from this class and gain the
    mandatory ``start_position`` and ``end_position`` fields that record
    the exact span of source text the node was derived from.

    The ``frozen=True`` flag from :func:`dataclasses.dataclass` ensures
    that all instances are immutable after construction; attribute
    assignment will raise :class:`dataclasses.FrozenInstanceError`.

    Attributes:
        start_position:
            The :class:`~app.parser.lexer.position.Position` of the
            first character of the syntactic construct this node
            represents.
        end_position:
            The :class:`~app.parser.lexer.position.Position` of the
            last character of the syntactic construct this node
            represents.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> # ASTNode is abstract — instantiate a concrete subclass.
    """

    start_position: Position
    end_position: Position

    @abstractmethod
    def accept(self, visitor: object) -> object:
        """
        Accept a visitor and dispatch to the appropriate ``visit_*`` method.

        Concrete subclasses override this to call the specific visitor
        method that matches their node type (e.g. ``visitor.visit_program``).

        Args:
            visitor:
                An :class:`~app.parser.ast.visitor.ASTVisitor` instance (or
                any object implementing the visitor protocol).

        Returns:
            Whatever the visitor method returns.
        """
