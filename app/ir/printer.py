"""
IR Pretty Printer.

Purpose:
    Provide a deterministic, human-readable text representation of an
    :class:`~app.ir.program.IRProgram` and its nested nodes.

    The pretty printer is a pure function — it never modifies the IR and
    produces identical output for identical input.

Responsibilities:
    - Format :class:`~app.ir.program.IRProgram`, :class:`~app.ir.program.IRModule`,
      :class:`~app.ir.program.IRFunction`, and :class:`~app.ir.blocks.IRBasicBlock`
      nodes with consistent indentation.
    - Format every concrete :class:`~app.ir.instructions.IRInstruction` subclass
      into a readable one-line string.
    - Expose a single public function :func:`pretty_print` that returns the
      complete IR as a ``str``.

Non-responsibilities:
    - Lexing, parsing, or semantic analysis.
    - Java code generation.
    - Optimisation or IR transformation.

Dependencies:
    - :mod:`app.ir.program`       — ``IRProgram``, ``IRModule``, ``IRFunction``.
    - :mod:`app.ir.blocks`        — ``IRBasicBlock``.
    - :mod:`app.ir.instructions`  — all concrete instruction types.
    - Python standard library only.

Examples:
    Pretty-printing a compiled program::

        from app.ir.printer import pretty_print

        text = pretty_print(ir_program)
        print(text)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRAssignment,
    IRCall,
    IRConditionalBranch,
    IRDisplay,
    IRDivide,
    IRInstruction,
    IRJump,
    IRMove,
    IRMultiply,
    IRReturn,
    IRSubtract,
)
from app.ir.program import IRFunction, IRModule, IRProgram

__all__ = ["pretty_print"]

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def pretty_print(program: IRProgram) -> str:
    """
    Return a deterministic, human-readable string representation of *program*.

    The format is::

        Program <name>

          Module <name>

            Function <name>

              <block-label>:
                <instruction>
                ...

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` to format.

    Returns:
        A non-empty ``str`` ready for printing.
    """
    lines: list[str] = []
    lines.append(f"Program {program.name}")

    for module in program.modules:
        lines.append("")
        _format_module(module, lines)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal formatters
# ---------------------------------------------------------------------------


def _format_module(module: IRModule, lines: list[str]) -> None:
    """Append module representation to *lines*."""
    lines.append(f"  Module {module.name}")

    for function in module.functions:
        lines.append("")
        _format_function(function, lines)


def _format_function(function: IRFunction, lines: list[str]) -> None:
    """Append function representation to *lines*."""
    lines.append(f"    Function {function.name}")

    for block in function.blocks:
        lines.append("")
        _format_block(block, lines)


def _format_block(block: IRBasicBlock, lines: list[str]) -> None:
    """Append basic-block representation to *lines*."""
    label = block.label or block.name or "<block>"
    lines.append(f"      {label}:")

    if not block.instructions:
        lines.append("        ; (empty block)")
    else:
        for instr in block.instructions:
            lines.append(f"        {_format_instruction(instr)}")


def _format_instruction(instr: IRInstruction) -> str:
    """Return a single-line string for *instr*."""
    if isinstance(instr, IRMove):
        return f"MOVE {instr.source} -> {instr.result}"

    if isinstance(instr, IRAssignment):
        return f"ASSIGN {instr.result} = {instr.value}"

    if isinstance(instr, IRDisplay):
        return f"DISPLAY {instr.operand}"

    if isinstance(instr, IRAccept):
        return f"ACCEPT {instr.result}"

    if isinstance(instr, IRAdd):
        return f"ADD {instr.left} TO {instr.right}"

    if isinstance(instr, IRSubtract):
        return f"SUBTRACT {instr.left} FROM {instr.right}"

    if isinstance(instr, IRMultiply):
        return f"MULTIPLY {instr.left} BY {instr.right}"

    if isinstance(instr, IRDivide):
        return f"DIVIDE {instr.left} INTO {instr.right}"

    if isinstance(instr, IRCall):
        args_str = " ".join(instr.args) if instr.args else ""
        if args_str:
            return f"CALL {instr.target} USING {args_str}"
        return f"CALL {instr.target}"

    if isinstance(instr, IRReturn):
        if instr.operand:
            return f"RETURN {instr.operand}"
        return "RETURN"

    if isinstance(instr, IRConditionalBranch):
        return f"IF {instr.condition} THEN {instr.then_target} ELSE {instr.else_target}"

    if isinstance(instr, IRJump):
        return f"JUMP {instr.target}"

    # Fallback for unknown instruction subtypes
    return f"; {type(instr).__name__}(result={instr.result!r})"
