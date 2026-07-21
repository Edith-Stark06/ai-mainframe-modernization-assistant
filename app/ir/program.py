"""
IR Program, Module, and Function.

Purpose:
    Define the top-level structural IR nodes:

    * :class:`IRProgram`  — top-level compilation unit; contains one or more
      :class:`IRModule` objects.
    * :class:`IRModule`   — a logical grouping of :class:`IRFunction` objects,
      roughly corresponding to a COBOL compilation unit or a generated Java
      class.
    * :class:`IRFunction` — a callable unit containing one or more
      :class:`~app.ir.blocks.IRBasicBlock` objects; corresponds to a COBOL
      paragraph, section, or sub-program entry point.

    These nodes form the skeleton of every compiled program.  They are
    populated by the AST-to-IR translation pass (TASK-025+) and consumed
    by the code-generation back-end.

Responsibilities:
    - Immutable, frozen dataclass definitions for ``IRProgram``,
      ``IRModule``, and ``IRFunction``.
    - ``__len__`` helpers for child-count queries.
    - ``accept()`` methods for visitor dispatch.

Non-responsibilities:
    - AST-to-IR translation.
    - Type checking or semantic validation.
    - Java code generation.

Dependencies:
    - :mod:`app.ir.nodes`  — ``IRNode``, ``IRNodeKind``.
    - :mod:`app.ir.blocks` — ``IRBasicBlock`` (TYPE_CHECKING only).
    - Python standard library only (``dataclasses``).

Examples:
    Building a minimal program skeleton::

        from app.ir.program import IRProgram, IRModule, IRFunction
        from app.ir.blocks import IRBasicBlock

        bb = IRBasicBlock(label="entry")
        fn = IRFunction(name="MAIN", blocks=(bb,))
        mod = IRModule(name="PAYROLL", functions=(fn,))
        prog = IRProgram(name="PAYROLL-SYSTEM", modules=(mod,))

        len(prog)          # 1 module
        len(prog.modules[0])  # 1 function
        len(fn)            # 1 basic block

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.ir.nodes import IRNode, IRNodeKind

if TYPE_CHECKING:
    from app.ir.blocks import IRBasicBlock

__all__ = [
    "IRFunction",
    "IRModule",
    "IRProgram",
]


# ---------------------------------------------------------------------------
# IRFunction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRFunction(IRNode):
    """
    A callable unit of IR code composed of one or more
    :class:`~app.ir.blocks.IRBasicBlock` objects.

    An :class:`IRFunction` maps to a COBOL paragraph, section, or
    sub-program entry point.  In the Java back-end it will correspond to
    a method.

    Attributes:
        kind:
            Always :attr:`~app.ir.nodes.IRNodeKind.FUNCTION`.
        name:
            Unique name of this function within its module (e.g.
            ``"MAIN"``, ``"PROCESS-RECORD"``).
        blocks:
            An ordered, immutable tuple of
            :class:`~app.ir.blocks.IRBasicBlock` objects.  The first
            block is the entry point.
        params:
            Ordered parameter names for future typed argument support.
        return_type:
            Human-readable return type hint (e.g. ``"void"``,
            ``"numeric"``).  Not enforced at this layer.

    Examples:
        >>> from app.ir.program import IRFunction
        >>> fn = IRFunction(name="MAIN")
        >>> fn.name
        'MAIN'
        >>> fn.blocks
        ()
        >>> len(fn)
        0
    """

    kind: IRNodeKind = field(default=IRNodeKind.FUNCTION, init=False)
    blocks: tuple[IRBasicBlock, ...] = field(default_factory=tuple)
    params: tuple[str, ...] = field(default_factory=tuple)
    return_type: str = field(default="void")

    def __len__(self) -> int:
        """Return the number of basic blocks in this function."""
        return len(self.blocks)

    def accept(self, visitor: Any) -> Any:
        """
        Dispatch to ``visitor.visit_function(self)``.

        Args:
            visitor: An :class:`~app.ir.visitors.IRVisitor` or compatible object.

        Returns:
            The visitor method's return value, or ``None``.
        """
        visit = getattr(visitor, "visit_function", None)
        if callable(visit):
            return visit(self)
        return None


# ---------------------------------------------------------------------------
# IRModule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRModule(IRNode):
    """
    A logical grouping of :class:`IRFunction` objects.

    An :class:`IRModule` roughly corresponds to a COBOL compilation unit
    (a single source file) or a generated Java class.  A module groups
    all functions belonging to the same logical component.

    Attributes:
        kind:
            Always :attr:`~app.ir.nodes.IRNodeKind.MODULE`.
        name:
            Unique name of this module (e.g. ``"PAYROLL"``).
        functions:
            An ordered, immutable tuple of :class:`IRFunction` objects.

    Examples:
        >>> from app.ir.program import IRModule
        >>> mod = IRModule(name="PAYROLL")
        >>> mod.name
        'PAYROLL'
        >>> len(mod)
        0
    """

    kind: IRNodeKind = field(default=IRNodeKind.MODULE, init=False)
    functions: tuple[IRFunction, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        """Return the number of functions in this module."""
        return len(self.functions)

    def accept(self, visitor: Any) -> Any:
        """
        Dispatch to ``visitor.visit_module(self)``.

        Args:
            visitor: An :class:`~app.ir.visitors.IRVisitor` or compatible object.

        Returns:
            The visitor method's return value, or ``None``.
        """
        visit = getattr(visitor, "visit_module", None)
        if callable(visit):
            return visit(self)
        return None


# ---------------------------------------------------------------------------
# IRProgram
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRProgram(IRNode):
    """
    Top-level IR node representing a complete compilation unit.

    An :class:`IRProgram` is the root of every IR tree.  It contains one
    or more :class:`IRModule` objects.  In a typical COBOL modernisation
    pipeline a single program maps to a single module which maps to one
    or more functions (paragraphs).

    Attributes:
        kind:
            Always :attr:`~app.ir.nodes.IRNodeKind.PROGRAM`.
        name:
            Human-readable name of the program (e.g.
            ``"PAYROLL-SYSTEM"``).
        modules:
            An ordered, immutable tuple of :class:`IRModule` objects.

    Examples:
        >>> from app.ir.program import IRProgram
        >>> prog = IRProgram(name="PAYROLL-SYSTEM")
        >>> prog.name
        'PAYROLL-SYSTEM'
        >>> len(prog)
        0
        >>> prog.modules
        ()
    """

    kind: IRNodeKind = field(default=IRNodeKind.PROGRAM, init=False)
    modules: tuple[IRModule, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        """Return the number of modules in this program."""
        return len(self.modules)

    def accept(self, visitor: Any) -> Any:
        """
        Dispatch to ``visitor.visit_program(self)``.

        Args:
            visitor: An :class:`~app.ir.visitors.IRVisitor` or compatible object.

        Returns:
            The visitor method's return value, or ``None``.
        """
        visit = getattr(visitor, "visit_program", None)
        if callable(visit):
            return visit(self)
        return None
