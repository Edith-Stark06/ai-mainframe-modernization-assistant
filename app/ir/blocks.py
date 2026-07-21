"""
IR Basic Block.

Purpose:
    Define :class:`IRBasicBlock` — a straight-line sequence of
    :class:`~app.ir.instructions.IRInstruction` objects with a single entry
    point and a single exit point.

    A basic block is the fundamental unit of control-flow analysis.  Every
    instruction in a basic block executes in order; only the final instruction
    may transfer control elsewhere (via :class:`~app.ir.instructions.IRBranch`
    or :class:`~app.ir.instructions.IRReturn`).

Responsibilities:
    - :class:`IRBasicBlock` — immutable sequence of instructions; carries a
      ``label`` that uniquely identifies it within a function.
    - Provide a ``__len__`` convenience for instruction-count checks.
    - Expose :meth:`accept` for visitor dispatch.

Non-responsibilities:
    - Control-flow graph construction (successor/predecessor tracking).
    - Dominance analysis.
    - SSA construction.

Dependencies:
    - :mod:`app.ir.nodes`        — ``IRNode``, ``IRNodeKind``.
    - :mod:`app.ir.instructions` — ``IRInstruction``.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a basic block with two instructions::

        from app.ir.instructions import IRMove, IRReturn
        from app.ir.blocks import IRBasicBlock

        bb = IRBasicBlock(
            label="MAIN-BODY",
            instructions=(
                IRMove(result="WS-OUT", source="WS-IN"),
                IRReturn(),
            ),
        )
        len(bb)           # 2
        bb.label          # 'MAIN-BODY'
        bb.instructions   # (IRMove(...), IRReturn())

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
    from app.ir.instructions import IRInstruction

__all__ = ["IRBasicBlock"]


@dataclass(frozen=True)
class IRBasicBlock(IRNode):
    """
    An immutable, straight-line sequence of
    :class:`~app.ir.instructions.IRInstruction` objects.

    A basic block has a single entry (its ``label``) and a single exit
    (the last instruction, which should be a branch or return for a well-formed
    function).  Instructions inside the block execute unconditionally in order.

    Attributes:
        kind:
            Always :attr:`~app.ir.nodes.IRNodeKind.BASIC_BLOCK`.
        name:
            Alias for ``label``; inherited from :class:`~app.ir.nodes.IRNode`.
        label:
            Unique identifier for this block within its function (e.g.
            ``"entry"``, ``"MAIN-LOOP"``, ``"EOF-HANDLER"``).
        instructions:
            An ordered, immutable tuple of
            :class:`~app.ir.instructions.IRInstruction` objects.

    Examples:
        >>> from app.ir.blocks import IRBasicBlock
        >>> bb = IRBasicBlock(label="entry")
        >>> bb.label
        'entry'
        >>> bb.instructions
        ()
        >>> len(bb)
        0
    """

    kind: IRNodeKind = field(default=IRNodeKind.BASIC_BLOCK, init=False)
    label: str = field(default="")
    instructions: tuple[IRInstruction, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Sync ``name`` with ``label`` for uniform diagnostics."""
        # dataclass is frozen — use object.__setattr__ to set name.
        object.__setattr__(self, "name", self.label)

    def __len__(self) -> int:
        """Return the number of instructions in this block."""
        return len(self.instructions)

    def accept(self, visitor: Any) -> Any:
        """
        Dispatch to ``visitor.visit_basic_block(self)``.

        Args:
            visitor: An :class:`~app.ir.visitors.IRVisitor` or compatible object.

        Returns:
            The visitor method's return value, or ``None``.
        """
        visit = getattr(visitor, "visit_basic_block", None)
        if callable(visit):
            return visit(self)
        return None
