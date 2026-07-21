"""
IR Instruction Hierarchy.

Purpose:
    Define the immutable instruction types that populate
    :class:`~app.ir.blocks.IRBasicBlock` instances.  Instructions represent
    the atomic executable operations of the IR — data movement, function
    calls, control flow, and return from a function.

    The instruction hierarchy is designed as a set of frozen dataclasses so
    that instructions can be compared, hashed, and safely shared across
    analyses.

Responsibilities:
    - :class:`IRInstruction` — abstract base for all instructions; carries a
      ``result`` operand name (empty string if the instruction produces no value)
      and an optional human-readable ``comment``.
    - :class:`IRAssignment` — assigns a constant or computed value to a name.
    - :class:`IRMove`       — copies the value of one named operand to another.
    - :class:`IRCall`       — represents a (potentially impure) function call
      with zero or more arguments; result may be discarded.
    - :class:`IRReturn`     — terminates the enclosing function; carries an
      optional return operand name.
    - :class:`IRBranch`     — unconditional or conditional transfer of control
      to a target label.

Non-responsibilities:
    - Instruction scheduling or register allocation.
    - COBOL-specific semantics.
    - Java code generation.
    - Optimisation passes.

Dependencies:
    - :mod:`app.ir.nodes` — ``IRNode``, ``IRNodeKind``.
    - Python standard library only (``abc``, ``dataclasses``).

Examples:
    Constructing a MOVE instruction::

        from app.ir.instructions import IRMove
        mv = IRMove(result="WS-TARGET", source="WS-SOURCE")
        mv.kind.value  # 'instruction'
        mv.result      # 'WS-TARGET'
        mv.source      # 'WS-SOURCE'

    Constructing a CALL instruction::

        from app.ir.instructions import IRCall
        call = IRCall(result="RETVAL", target="PROCESS-RECORD", args=("ARG1",))

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.ir.nodes import IRNode, IRNodeKind

__all__ = [
    "IRAssignment",
    "IRBranch",
    "IRCall",
    "IRInstruction",
    "IRMove",
    "IRReturn",
]


# ---------------------------------------------------------------------------
# Abstract instruction base
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRInstruction(IRNode):
    """
    Abstract base for all IR instructions.

    An instruction is an atomic executable operation that belongs to a
    :class:`~app.ir.blocks.IRBasicBlock`.  Every instruction has:

    * a ``kind`` fixed to :attr:`~app.ir.nodes.IRNodeKind.INSTRUCTION`.
    * an optional ``result`` — the name of the operand that receives the
      output (empty string if no value is produced).
    * an optional ``comment`` for debugging and documentation.

    Subclasses provide instruction-specific operand fields.

    Attributes:
        kind:
            Always :attr:`~app.ir.nodes.IRNodeKind.INSTRUCTION`.
        result:
            Name of the operand that receives the instruction's output.
            Empty string if the instruction produces no value (e.g.
            :class:`IRReturn`, void :class:`IRCall`).
        comment:
            Optional human-readable annotation for logging and dumps.

    Examples:
        >>> from app.ir.instructions import IRMove
        >>> mv = IRMove(result="WS-OUT", source="WS-IN")
        >>> mv.kind.value
        'instruction'
        >>> mv.result
        'WS-OUT'
    """

    kind: IRNodeKind = field(default=IRNodeKind.INSTRUCTION, init=False)
    result: str = field(default="")
    comment: str = field(default="")

    @abstractmethod
    def accept(self, visitor: Any) -> Any:
        """
        Dispatch to the visitor method appropriate for this instruction.

        Args:
            visitor: An :class:`~app.ir.visitors.IRVisitor` or compatible object.

        Returns:
            The visitor method's return value, or ``None``.
        """


# ---------------------------------------------------------------------------
# Concrete instructions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRAssignment(IRInstruction):
    """
    Assign a literal or constant value to a named result operand.

    Use :class:`IRAssignment` when the value being stored is a literal
    constant (an integer, string literal, or COBOL figurative constant)
    rather than the content of another operand.

    Attributes:
        result:
            Name of the target operand (e.g. ``"WS-COUNT"``).
        value:
            The literal value as a string (e.g. ``"0"``, ``'"HELLO"'``,
            ``"SPACES"``).
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRAssignment
        >>> a = IRAssignment(result="WS-COUNT", value="0")
        >>> a.value
        '0'
        >>> a.result
        'WS-COUNT'
    """

    value: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_assignment(self)``."""
        visit = getattr(visitor, "visit_assignment", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRMove(IRInstruction):
    """
    Copy the value of one named operand to another.

    :class:`IRMove` corresponds to a COBOL ``MOVE source TO target`` statement
    where both operands are data-name references (after type checking has
    verified compatibility).

    Attributes:
        result:
            Name of the destination operand (``target`` in COBOL terms).
        source:
            Name of the source operand.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRMove
        >>> mv = IRMove(result="WS-TARGET", source="WS-SOURCE")
        >>> mv.source
        'WS-SOURCE'
        >>> mv.result
        'WS-TARGET'
    """

    source: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_move(self)``."""
        visit = getattr(visitor, "visit_move", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRCall(IRInstruction):
    """
    Invoke a named function or paragraph with zero or more arguments.

    :class:`IRCall` captures a call to a named target (a COBOL paragraph,
    sub-program, or a generated Java method).  The call may produce a result
    value (stored in ``result``) or may be void (``result = ""``).

    Attributes:
        result:
            Name of the operand that receives the return value.  Set to
            ``""`` for void calls.
        target:
            Name of the function or paragraph to invoke.
        args:
            Positional argument names, in order.  Default: empty tuple.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRCall
        >>> call = IRCall(target="PROCESS-RECORD", args=("EMP-ID", "EMP-NAME"))
        >>> call.target
        'PROCESS-RECORD'
        >>> call.args
        ('EMP-ID', 'EMP-NAME')
    """

    target: str = field(default="")
    args: tuple[str, ...] = field(default_factory=tuple)

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_call(self)``."""
        visit = getattr(visitor, "visit_call", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRReturn(IRInstruction):
    """
    Terminate the enclosing function and optionally return a value.

    :class:`IRReturn` corresponds to a COBOL ``STOP RUN`` or ``GOBACK``
    statement.  The optional ``operand`` names the value to return; for
    void functions it is left empty.

    Attributes:
        result:
            Unused (always ``""``); inherited from :class:`IRInstruction`.
        operand:
            Name of the operand whose value is returned, or ``""`` for
            void returns.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRReturn
        >>> ret = IRReturn(operand="WS-RESULT")
        >>> ret.operand
        'WS-RESULT'
        >>> IRReturn().operand
        ''
    """

    operand: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_return(self)``."""
        visit = getattr(visitor, "visit_return", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRBranch(IRInstruction):
    """
    Transfer control to a target label, conditionally or unconditionally.

    :class:`IRBranch` models both unconditional jumps (``condition = ""``)
    and conditional branches (``condition`` names a boolean-valued operand).

    Attributes:
        result:
            Unused (always ``""``); inherited from :class:`IRInstruction`.
        target:
            Name of the label or basic block to jump to.
        condition:
            Name of the operand that controls the branch.  Empty string
            denotes an unconditional branch.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRBranch
        >>> jmp = IRBranch(target="MAIN-EXIT")
        >>> jmp.target
        'MAIN-EXIT'
        >>> jmp.condition
        ''
        >>> cond = IRBranch(target="EOF-HANDLER", condition="WS-EOF-FLAG")
        >>> cond.condition
        'WS-EOF-FLAG'
    """

    target: str = field(default="")
    condition: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_branch(self)``."""
        visit = getattr(visitor, "visit_branch", None)
        if callable(visit):
            return visit(self)
        return None
