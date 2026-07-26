"""
Java Statement Emitter.

Purpose:
    Translate individual IR instructions into executable Java statement strings.

    This module is the authoritative translation layer between the IR instruction
    hierarchy and Java statement syntax.  Each ``emit_*`` function accepts a single
    IR instruction and returns one or more Java source lines (without indentation).

    TASK-034 added support for :class:`~app.ir.instructions.IRMove` and
    :class:`~app.ir.instructions.IRDisplay`.

    TASK-035 extends translation to the four arithmetic IR instructions:
    :class:`~app.ir.instructions.IRAdd`,
    :class:`~app.ir.instructions.IRSubtract`,
    :class:`~app.ir.instructions.IRMultiply`, and
    :class:`~app.ir.instructions.IRDivide`.

    TASK-036 extends translation to structured control-flow IR instructions:
    :class:`~app.ir.instructions.IRIf`,
    :class:`~app.ir.instructions.IRElse`, and
    :class:`~app.ir.instructions.IREndIf`.  These are dispatched at *depth 0*
    by :func:`emit_statement`; the full depth-aware path used by
    :func:`~app.backend.java.generator._collect_statements` calls
    :func:`~app.backend.java.control_flow_emitter.emit_if` directly.

    All other instruction types produce a ``// TODO:`` stub and a ``BE005``
    WARNING diagnostic so generation continues gracefully.

Design:
    Operand translation is shared across all emitters via the private helper
    :func:`_translate_operand`, which converts an IR operand string into the
    equivalent Java expression:

    * Quoted string literals (``"..."`` in the IR) → emitted as-is.
    * Pure numeric strings (integer or decimal, optional sign) → emitted as-is.
    * Otherwise → treated as COBOL identifier, converted to lowerCamelCase via
      :func:`~app.backend.java.naming.to_java_field_name`.

    Arithmetic instructions follow the compound-assignment pattern — the
    destination (``instruction.result``) receives the in-place operation:

    +--------------+-------------------+----------------------------------+
    | IR type      | Operator          | Generated Java                   |
    +==============+===================+==================================+
    | ``IRAdd``    | ``+=``            | ``<result> += <left>;``          |
    +--------------+-------------------+----------------------------------+
    | ``IRSubtract``| ``-=``           | ``<result> -= <left>;``          |
    +--------------+-------------------+----------------------------------+
    | ``IRMultiply``| ``*=``           | ``<result> *= <left>;``          |
    +--------------+-------------------+----------------------------------+
    | ``IRDivide`` | ``/=``            | ``<result> /= <left>;``          |
    +--------------+-------------------+----------------------------------+

    For all arithmetic instructions ``instruction.result`` is the accumulator
    variable and ``instruction.left`` is the operand applied to it.
    ``instruction.right`` is reserved for future multi-operand forms; if it is
    non-empty and differs from ``result``, a ``BE006`` WARNING diagnostic is
    emitted (graceful degradation).

Responsibilities:
    - :func:`emit_statement`  — dispatcher: routes an ``IRInstruction`` to the
      correct ``emit_*`` function.
    - :func:`emit_move`       — MOVE → Java assignment.
    - :func:`emit_display`    — DISPLAY → ``System.out.println()``.
    - :func:`emit_add`        — ADD → ``+=`` compound assignment.
    - :func:`emit_subtract`   — SUBTRACT → ``-=`` compound assignment.
    - :func:`emit_multiply`   — MULTIPLY → ``*=`` compound assignment.
    - :func:`emit_divide`     — DIVIDE → ``/=`` compound assignment.
    - Produce :class:`~app.backend.java.generator.BackendDiagnostic` records
      for unsupported instructions or malformed operands.

Non-responsibilities:
    - Control-flow translation (deferred).
    - CALL translation (deferred).
    - Field declaration generation (:mod:`app.backend.java.field_model`).
    - Indentation management (handled by the caller).

Dependencies:
    - :mod:`app.ir.instructions` — ``IRInstruction``, ``IRMove``, ``IRDisplay``,
      ``IRAdd``, ``IRSubtract``, ``IRMultiply``, ``IRDivide``.
    - :mod:`app.backend.java.naming` — :func:`to_java_field_name`.
    - :mod:`app.backend.java.generator` — ``BackendDiagnostic``, ``BackendSeverity``.

Examples:
    Translating a DISPLAY instruction::

        from app.ir.instructions import IRDisplay, IRMove
        from app.backend.java.statement_emitter import emit_statement

        diags = []
        stmts = emit_statement(IRDisplay(operand='"HELLO"'), diags)
        # stmts == ['System.out.println("HELLO");']

        stmts2 = emit_statement(IRMove(result="WS-COUNT", source="1"), diags)
        # stmts2 == ['wsCount = 1;']

    Translating an ADD instruction::

        from app.ir.instructions import IRAdd
        from app.backend.java.statement_emitter import emit_add

        diags = []
        stmts = emit_add(IRAdd(result="WS-COUNT", left="5"), diags)
        # stmts == ['wsCount += 5;']

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re

from app.backend.java.control_flow_emitter import (
    emit_else,
    emit_end_if,
    emit_end_perform,
    emit_if,
    emit_perform_until,
)
from app.backend.java.generator import BackendDiagnostic, BackendSeverity
from app.backend.java.naming import to_java_field_name
from app.ir.instructions import (
    IRAdd,
    IRDisplay,
    IRDivide,
    IRElse,
    IREndIf,
    IREndPerform,
    IRIf,
    IRInstruction,
    IRMove,
    IRMultiply,
    IRPerformUntil,
    IRSubtract,
)

__all__ = [
    "emit_add",
    "emit_display",
    "emit_divide",
    "emit_else",
    "emit_end_if",
    "emit_end_perform",
    "emit_if",
    "emit_move",
    "emit_multiply",
    "emit_perform_until",
    "emit_statement",
    "emit_subtract",
]


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def emit_statement(
    instruction: IRInstruction,
    diagnostics: list[BackendDiagnostic],
    depth: int = 0,
) -> list[str]:
    """
    Translate *instruction* into one or more Java statement strings.

    Supported instruction types:

    * :class:`~app.ir.instructions.IRMove`     → Java assignment (``=``).
    * :class:`~app.ir.instructions.IRDisplay`  → ``System.out.println()``.
    * :class:`~app.ir.instructions.IRAdd`      → ``+=`` compound assignment.
    * :class:`~app.ir.instructions.IRSubtract` → ``-=`` compound assignment.
    * :class:`~app.ir.instructions.IRMultiply` → ``*=`` compound assignment.
    * :class:`~app.ir.instructions.IRDivide`   → ``/=`` compound assignment.
    * :class:`~app.ir.instructions.IRIf`       → ``if (<cond>) {`` (at *depth*).
    * :class:`~app.ir.instructions.IRElse`     → ``} else {`` (at *depth*).
    * :class:`~app.ir.instructions.IREndIf`    → ``}`` (at *depth*).
    * :class:`~app.ir.instructions.IRPerformUntil` → ``while (!(<cond>)) {`` (at *depth*).
    * :class:`~app.ir.instructions.IREndPerform` → ``}`` (at *depth*).

    All other instructions produce a ``// TODO: <type>`` comment and a
    ``BE005`` WARNING so that generation continues rather than failing.

    .. note::
        When called from :func:`~app.backend.java.generator._collect_statements`,
        control-flow instructions are handled by the depth-aware loop *before*
        reaching this dispatcher.  The ``depth`` parameter here is used only
        when callers invoke :func:`emit_statement` directly (e.g., unit tests).

    Args:
        instruction:
            The IR instruction to lower.
        diagnostics:
            Mutable list; backend diagnostics are appended here.
        depth:
            Nesting depth for control-flow instructions.  Defaults to ``0``
            (directly inside ``main()``).

    Returns:
        A list of Java statement strings (no base indentation).  May be
        empty if the instruction produces nothing (e.g. a void no-op).
    """
    # Lazy import to avoid circular dependency:
    # control_flow_emitter → statement_emitter._translate_operand
    from app.backend.java.control_flow_emitter import (
        emit_else as _emit_else,
        emit_end_if as _emit_end_if,
        emit_end_perform as _emit_end_perform,
        emit_if as _emit_if,
        emit_perform_until as _emit_perform_until,
    )

    if isinstance(instruction, IRMove):
        return emit_move(instruction, diagnostics)

    if isinstance(instruction, IRDisplay):
        return emit_display(instruction, diagnostics)

    if isinstance(instruction, IRAdd):
        return emit_add(instruction, diagnostics)

    if isinstance(instruction, IRSubtract):
        return emit_subtract(instruction, diagnostics)

    if isinstance(instruction, IRMultiply):
        return emit_multiply(instruction, diagnostics)

    if isinstance(instruction, IRDivide):
        return emit_divide(instruction, diagnostics)

    if isinstance(instruction, IRIf):
        return _emit_if(instruction, depth, diagnostics)

    if isinstance(instruction, IRElse):
        return _emit_else(depth, diagnostics)

    if isinstance(instruction, IREndIf):
        return _emit_end_if(depth, diagnostics)

    if isinstance(instruction, IRPerformUntil):
        return _emit_perform_until(instruction, depth, diagnostics)

    if isinstance(instruction, IREndPerform):
        return _emit_end_perform(depth, diagnostics)

    # Unsupported — emit a TODO comment and a WARNING diagnostic
    type_name = type(instruction).__name__
    diagnostics.append(
        BackendDiagnostic(
            severity=BackendSeverity.WARNING,
            message=(
                f"unsupported IR instruction '{type_name}'; " "emitting TODO comment."
            ),
            code="BE005",
        )
    )
    return [f"// TODO: translate {type_name}"]


# ---------------------------------------------------------------------------
# MOVE → Java assignment
# ---------------------------------------------------------------------------


def emit_move(
    instruction: IRMove,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRMove` into a Java assignment.

    The destination (``instruction.result``) is converted to lowerCamelCase.
    The source (``instruction.source``) is translated via
    :func:`_translate_operand`.

    Rules:
        - ``MOVE "HELLO" -> WS-GREETING`` → ``wsGreeting = "HELLO";``
        - ``MOVE 42 -> WS-COUNT``         → ``wsCount = 42;``
        - ``MOVE WS-A -> WS-B``           → ``wsB = wsA;``

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRMove` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.

    Returns:
        A list containing exactly one Java assignment string, or an empty
        list when the instruction is invalid.
    """
    target = instruction.result
    source = instruction.source

    if not target:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRMove has empty result (target); skipping.",
                code="BE004",
            )
        )
        return []

    if not source:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(f"IRMove to '{target}' has empty source; skipping."),
                code="BE004",
            )
        )
        return []

    java_target = to_java_field_name(target)
    java_source = _translate_operand(source)

    return [f"{java_target} = {java_source};"]


# ---------------------------------------------------------------------------
# DISPLAY → System.out.println()
# ---------------------------------------------------------------------------


def emit_display(
    instruction: IRDisplay,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRDisplay` into a Java
    ``System.out.println()`` call.

    Rules:
        - ``DISPLAY "HELLO"``    → ``System.out.println("HELLO");``
        - ``DISPLAY WS-NAME``    → ``System.out.println(wsName);``
        - ``DISPLAY 42``         → ``System.out.println(42);``

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRDisplay` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.

    Returns:
        A list containing exactly one ``System.out.println(...)`` string, or
        an empty list when the operand is missing.
    """
    operand = instruction.operand

    if not operand:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRDisplay has empty operand; skipping.",
                code="BE004",
            )
        )
        return []

    java_operand = _translate_operand(operand)
    return [f"System.out.println({java_operand});"]


# ---------------------------------------------------------------------------
# ADD → += compound assignment
# ---------------------------------------------------------------------------


def emit_add(
    instruction: IRAdd,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRAdd` into a Java ``+=``
    compound assignment.

    The IR arithmetic convention is:

    * ``instruction.result`` — the accumulator variable (destination).
    * ``instruction.left``   — the operand to add to the accumulator.

    Rules:
        - ``ADD 5 TO WS-COUNT``          → ``wsCount += 5;``
        - ``ADD WS-VALUE TO WS-TOTAL``   → ``wsTotal += wsValue;``
        - ``ADD 3.14 TO WS-RATE``        → ``wsRate += 3.14;``

    A ``BE006`` WARNING is appended when ``instruction.result`` is empty,
    when ``instruction.left`` is empty, or when ``instruction.right`` is
    non-empty and differs from the result (indicating a multi-operand form
    that is not yet supported).

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRAdd` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.

    Returns:
        A list containing exactly one Java compound-assignment string, or an
        empty list when the instruction is malformed.
    """
    return _emit_arithmetic(instruction, "+=", "IRAdd", diagnostics)


# ---------------------------------------------------------------------------
# SUBTRACT → -= compound assignment
# ---------------------------------------------------------------------------


def emit_subtract(
    instruction: IRSubtract,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRSubtract` into a Java ``-=``
    compound assignment.

    Rules:
        - ``SUBTRACT 2 FROM WS-COUNT``       → ``wsCount -= 2;``
        - ``SUBTRACT WS-LOSS FROM WS-TOTAL`` → ``wsTotal -= wsLoss;``

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRSubtract` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.

    Returns:
        A list containing exactly one Java compound-assignment string, or an
        empty list when the instruction is malformed.
    """
    return _emit_arithmetic(instruction, "-=", "IRSubtract", diagnostics)


# ---------------------------------------------------------------------------
# MULTIPLY → *= compound assignment
# ---------------------------------------------------------------------------


def emit_multiply(
    instruction: IRMultiply,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRMultiply` into a Java ``*=``
    compound assignment.

    Rules:
        - ``MULTIPLY 2 BY WS-COUNT``       → ``wsCount *= 2;``
        - ``MULTIPLY WS-RATE BY WS-TOTAL`` → ``wsTotal *= wsRate;``

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRMultiply` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.

    Returns:
        A list containing exactly one Java compound-assignment string, or an
        empty list when the instruction is malformed.
    """
    return _emit_arithmetic(instruction, "*=", "IRMultiply", diagnostics)


# ---------------------------------------------------------------------------
# DIVIDE → /= compound assignment
# ---------------------------------------------------------------------------


def emit_divide(
    instruction: IRDivide,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRDivide` into a Java ``/=``
    compound assignment.

    Rules:
        - ``DIVIDE 2 INTO WS-TOTAL``       → ``wsTotal /= 2;``
        - ``DIVIDE WS-DIVISOR INTO WS-Q``  → ``wsQ /= wsDivisor;``

    Divide-by-zero detection is the responsibility of earlier compiler phases.
    The emitter generates the statement exactly as the IR represents it.

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRDivide` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.

    Returns:
        A list containing exactly one Java compound-assignment string, or an
        empty list when the instruction is malformed.
    """
    return _emit_arithmetic(instruction, "/=", "IRDivide", diagnostics)


# ---------------------------------------------------------------------------
# Shared arithmetic helper
# ---------------------------------------------------------------------------

# Type alias for arithmetic instructions (union of the four concrete types).
_ArithmeticInstruction = IRAdd | IRSubtract | IRMultiply | IRDivide


def _emit_arithmetic(
    instruction: _ArithmeticInstruction,
    operator: str,
    type_name: str,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Shared implementation for all four arithmetic compound-assignment emitters.

    Validates ``result`` (accumulator) and ``left`` (applied operand), then
    emits ``<java_result> <operator> <java_left>;``.

    Emits ``BE006`` WARNING when:

    * ``instruction.result`` is empty.
    * ``instruction.left`` is empty.
    * ``instruction.right`` is non-empty (reserved for multi-operand forms).

    Args:
        instruction:
            An arithmetic IR instruction with ``result``, ``left``, and
            ``right`` fields.
        operator:
            The Java compound-assignment operator (e.g. ``"+="``, ``"-="``).
        type_name:
            Human-readable IR type name used in diagnostic messages.
        diagnostics:
            Mutable list; diagnostics appended here.

    Returns:
        A list of zero or one Java statement strings.
    """
    result = instruction.result
    left = instruction.left
    right = instruction.right  # type: ignore[attr-defined]

    if not result:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"{type_name} has empty result (accumulator target); skipping."
                ),
                code="BE006",
            )
        )
        return []

    if not left:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"{type_name} to '{result}' has empty left operand; skipping."
                ),
                code="BE006",
            )
        )
        return []

    # Warn about unsupported multi-operand form (right != "" and right != result)
    if right and right != result:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"{type_name} carries a non-empty 'right' operand ('{right}') "
                    "that differs from 'result'; multi-operand arithmetic is not yet "
                    "supported — 'right' is ignored."
                ),
                code="BE006",
            )
        )

    java_result = to_java_field_name(result)
    java_left = _translate_operand(left)

    return [f"{java_result} {operator} {java_left};"]


# ---------------------------------------------------------------------------
# Shared operand translator
# ---------------------------------------------------------------------------


def _translate_operand(operand: str) -> str:
    """
    Convert an IR operand string into a Java expression string.

    Translation rules (applied in order):

    1. **Quoted string literal** — operand starts and ends with ``"``:
       returned unchanged (e.g. ``'"HELLO"'`` → ``'"HELLO"'``).
    2. **Numeric literal** — operand matches ``[-+]?[0-9]+(\\.?[0-9]*)``:\
       returned unchanged (e.g. ``'42'`` → ``'42'``).
    3. **Identifier** — everything else is treated as a COBOL name and
       converted to lowerCamelCase via
       :func:`~app.backend.java.naming.to_java_field_name`.

    Args:
        operand:
            An IR operand string such as ``'"HELLO"'``, ``'42'``, or
            ``'WS-GREETING'``.

    Returns:
        A Java expression string ready for embedding in a statement.

    Examples:
        >>> _translate_operand('"HELLO"')
        '"HELLO"'
        >>> _translate_operand('42')
        '42'
        >>> _translate_operand('WS-GREETING')
        'wsGreeting'
    """
    # 1. Quoted string literal
    if operand.startswith('"') and operand.endswith('"') and len(operand) >= 2:
        return operand

    # 2. Numeric literal (integer or decimal, optional sign)
    if re.match(r"^[+-]?\d+(\.\d+)?$", operand):
        return operand

    # 3. COBOL identifier → lowerCamelCase
    return to_java_field_name(operand)
