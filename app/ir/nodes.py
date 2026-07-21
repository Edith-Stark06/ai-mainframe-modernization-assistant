"""
IR (Intermediate Representation) Node Hierarchy.

Purpose:
    Define the immutable base class and metadata types for every node in the
    compiler's Intermediate Representation.  All concrete IR constructs inherit
    from :class:`IRNode`.

    The IR is the language-independent representation that sits between the
    semantic analysis phase (AST + semantic context) and the back-end code
    generation phase (Java / Spring Boot).  It models *program behaviour* in
    terms of operations, data flow, and control flow rather than COBOL syntax.

Responsibilities:
    - :class:`IRNodeKind` — enumeration of all IR node categories for fast
      kind-checking without ``isinstance`` chains.
    - :class:`IRNode` — abstract base for every IR node; carries a ``kind``
      and an optional ``name`` for diagnostics; supports the visitor pattern
      via :meth:`accept`.

Non-responsibilities:
    - COBOL-specific constructs.
    - Java-specific constructs.
    - AST node representation.
    - Optimisation or transformation passes.

Dependencies:
    - Python standard library only (``abc``, ``dataclasses``, ``enum``).

Examples:
    Subclassing IRNode (internal use):

        from app.ir.nodes import IRNode, IRNodeKind

        @dataclass(frozen=True)
        class MyNode(IRNode):
            kind: IRNodeKind = IRNodeKind.INSTRUCTION
            def accept(self, visitor):
                return visitor.visit_my_node(self)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any

__all__ = [
    "IRNode",
    "IRNodeKind",
]


# ---------------------------------------------------------------------------
# Node kind enumeration
# ---------------------------------------------------------------------------


@unique
class IRNodeKind(Enum):
    """
    Category tag for every IR node.

    Using a kind enum allows downstream code to branch on node category
    without an ``isinstance`` chain, and enables pattern-matching in
    Python 3.10+.

    Attributes:
        PROGRAM:      Top-level compilation unit (:class:`~app.ir.program.IRProgram`).
        MODULE:       A logical grouping of functions (:class:`~app.ir.program.IRModule`).
        FUNCTION:     A callable unit (:class:`~app.ir.program.IRFunction`).
        BASIC_BLOCK:  A straight-line sequence of instructions
                      (:class:`~app.ir.blocks.IRBasicBlock`).
        INSTRUCTION:  Any executable instruction
                      (:class:`~app.ir.instructions.IRInstruction` and subclasses).

    Examples:
        >>> IRNodeKind.PROGRAM.value
        'program'
    """

    PROGRAM = "program"
    MODULE = "module"
    FUNCTION = "function"
    BASIC_BLOCK = "basic_block"
    INSTRUCTION = "instruction"


# ---------------------------------------------------------------------------
# Abstract IR node base
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRNode(ABC):
    """
    Abstract, immutable base class for every node in the Intermediate
    Representation.

    All concrete IR nodes inherit from :class:`IRNode`.  Nodes are frozen
    dataclasses — once constructed they cannot be mutated.  Downstream
    passes produce *new* nodes rather than mutating existing ones.

    Subclasses must implement :meth:`accept` to dispatch to the appropriate
    visitor method, following the Visitor pattern.

    Attributes:
        kind:
            The :class:`IRNodeKind` category of this node.  Used for
            fast kind-checking without ``isinstance`` chains.
        name:
            An optional human-readable label attached to the node for
            diagnostics, logging, and serialisation.  Defaults to ``""``.

    Examples:
        >>> from app.ir.nodes import IRNodeKind
        >>> # Concrete subclasses are defined in sibling modules.
    """

    kind: IRNodeKind
    name: str = field(default="")

    @abstractmethod
    def accept(self, visitor: Any) -> Any:
        """
        Dispatch this node to the appropriate ``visit_*`` method of *visitor*.

        Every concrete IR node must override this method to call the
        matching hook on the visitor.  This is the Visitor pattern entry
        point.

        Args:
            visitor:
                Any object that implements ``visit_*`` methods for the
                nodes it understands (typically an
                :class:`~app.ir.visitors.IRVisitor` subclass).

        Returns:
            The return value of the visitor hook, or ``None``.
        """
