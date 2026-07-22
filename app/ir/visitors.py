"""
IR Visitor Framework.

Purpose:
    Provide a composable, extensible visitor infrastructure for traversing
    and processing the Intermediate Representation without embedding behaviour
    in IR node classes.

    The visitor pattern is the canonical mechanism for implementing compiler
    passes over the IR.  Each pass subclasses :class:`IRVisitor` and overrides
    only the ``visit_*`` hooks relevant to the analysis or transformation it
    performs.  Unoverridden hooks are no-ops by default.

    :func:`traverse_ir` is the reference top-down traversal driver that
    visits the complete IR tree in a deterministic, structure-preserving order.

Responsibilities:
    - :class:`IRVisitor` — abstract base visitor with no-op ``visit_*``
      implementations for every concrete IR node type.  Subclass to implement
      analysis passes.
    - :func:`traverse_ir` — drive a full top-down traversal of an
      :class:`~app.ir.program.IRProgram` using any :class:`IRVisitor`.
    - Preserve the open/closed principle: adding a new IR node type only
      requires adding a new ``visit_*`` method; existing visitors do not break.

Non-responsibilities:
    - Concrete analysis pass logic.
    - Mutation of IR nodes (all nodes are frozen).
    - Control-flow or data-flow analysis.

Dependencies:
    - :mod:`app.ir.nodes`        — ``IRNode``.
    - :mod:`app.ir.program`      — ``IRProgram``, ``IRModule``, ``IRFunction``.
    - :mod:`app.ir.blocks`       — ``IRBasicBlock``.
    - :mod:`app.ir.instructions` — all instruction types.
    - Python standard library only (``abc``).

Examples:
    Counting every instruction in an IR tree::

        from app.ir.visitors import IRVisitor, traverse_ir

        class InstructionCounter(IRVisitor):
            def __init__(self) -> None:
                self.count = 0

            def visit_assignment(self, node):
                self.count += 1

            def visit_move(self, node):
                self.count += 1

            def visit_call(self, node):
                self.count += 1

            def visit_return(self, node):
                self.count += 1

            def visit_branch(self, node):
                self.count += 1

        counter = InstructionCounter()
        traverse_ir(program, counter)
        counter.count  # total instruction count

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ir.blocks import IRBasicBlock
    from app.ir.instructions import (
        IRAccept,
        IRAssignment,
        IRBranch,
        IRCall,
        IRDisplay,
        IRInstruction,
        IRMove,
        IRReturn,
    )
    from app.ir.program import IRFunction, IRModule, IRProgram

__all__ = [
    "IRVisitor",
    "traverse_ir",
]


# ---------------------------------------------------------------------------
# Abstract IR visitor base
# ---------------------------------------------------------------------------


class IRVisitor:
    """
    Base visitor for the Intermediate Representation.

    Subclass :class:`IRVisitor` and override the ``visit_*`` methods for the
    node types your pass cares about.  All unoverridden hooks are no-ops that
    return ``None``.

    Hook naming convention:

    ================================  =====================================
    Hook                              IR node type
    ================================  =====================================
    ``visit_program``                 :class:`~app.ir.program.IRProgram`
    ``visit_module``                  :class:`~app.ir.program.IRModule`
    ``visit_function``                :class:`~app.ir.program.IRFunction`
    ``visit_basic_block``             :class:`~app.ir.blocks.IRBasicBlock`
    ``visit_assignment``              :class:`~app.ir.instructions.IRAssignment`
    ``visit_move``                    :class:`~app.ir.instructions.IRMove`
    ``visit_display``                 :class:`~app.ir.instructions.IRDisplay`
    ``visit_accept``                  :class:`~app.ir.instructions.IRAccept`
    ``visit_call``                    :class:`~app.ir.instructions.IRCall`
    ``visit_return``                  :class:`~app.ir.instructions.IRReturn`
    ``visit_branch``                  :class:`~app.ir.instructions.IRBranch`
    ``visit_instruction`` (fallback)  :class:`~app.ir.instructions.IRInstruction`
    ================================  =====================================

    Examples:
        >>> class Noop(IRVisitor): pass
        >>> v = Noop()
        >>> v.visit_program(None) is None
        True
    """

    # -- Program structure --------------------------------------------------

    def visit_program(self, node: IRProgram) -> Any:
        """
        Visit an :class:`~app.ir.program.IRProgram`.

        Args:
            node: The program node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_module(self, node: IRModule) -> Any:
        """
        Visit an :class:`~app.ir.program.IRModule`.

        Args:
            node: The module node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_function(self, node: IRFunction) -> Any:
        """
        Visit an :class:`~app.ir.program.IRFunction`.

        Args:
            node: The function node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_basic_block(self, node: IRBasicBlock) -> Any:
        """
        Visit an :class:`~app.ir.blocks.IRBasicBlock`.

        Args:
            node: The basic-block node.

        Returns:
            ``None`` by default.
        """
        return None

    # -- Instructions -------------------------------------------------------

    def visit_instruction(self, node: IRInstruction) -> Any:
        """
        Generic fallback hook for any instruction not handled by a specific hook.

        Args:
            node: The instruction node.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_assignment(self, node: IRAssignment) -> Any:
        """
        Visit an :class:`~app.ir.instructions.IRAssignment`.

        Args:
            node: The assignment instruction.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_move(self, node: IRMove) -> Any:
        """
        Visit an :class:`~app.ir.instructions.IRMove`.

        Args:
            node: The move instruction.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_call(self, node: IRCall) -> Any:
        """
        Visit an :class:`~app.ir.instructions.IRCall`.

        Args:
            node: The call instruction.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_return(self, node: IRReturn) -> Any:
        """
        Visit an :class:`~app.ir.instructions.IRReturn`.

        Args:
            node: The return instruction.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_branch(self, node: IRBranch) -> Any:
        """
        Visit an :class:`~app.ir.instructions.IRBranch`.

        Args:
            node: The branch instruction.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_display(self, node: IRDisplay) -> Any:
        """
        Visit an :class:`~app.ir.instructions.IRDisplay`.

        Args:
            node: The display instruction.

        Returns:
            ``None`` by default.
        """
        return None

    def visit_accept(self, node: IRAccept) -> Any:
        """
        Visit an :class:`~app.ir.instructions.IRAccept`.

        Args:
            node: The accept instruction.

        Returns:
            ``None`` by default.
        """
        return None


# ---------------------------------------------------------------------------
# Traversal driver
# ---------------------------------------------------------------------------


def traverse_ir(program: IRProgram, visitor: IRVisitor) -> None:
    """
    Drive a full top-down traversal of *program* using *visitor*.

    Traversal order::

        IRProgram
        └── IRModule  (×N)
            └── IRFunction  (×M)
                └── IRBasicBlock  (×K)
                    └── IRInstruction  (×J)

    Every node is visited before its children.  Instructions are dispatched
    via their own :meth:`~app.ir.nodes.IRNode.accept` method so that concrete
    instruction types call their specific visitor hooks.

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` root to traverse.
        visitor:
            The :class:`IRVisitor` instance to dispatch to.

    Examples:
        >>> from app.ir.visitors import IRVisitor, traverse_ir
        >>> from app.ir.program import IRProgram
        >>> traverse_ir(IRProgram(name="P"), IRVisitor())  # no-op
    """
    visitor.visit_program(program)

    for module in program.modules:
        visitor.visit_module(module)

        for function in module.functions:
            visitor.visit_function(function)

            for block in function.blocks:
                visitor.visit_basic_block(block)

                for instruction in block.instructions:
                    # Let each concrete instruction dispatch to its specific hook.
                    instruction.accept(visitor)
