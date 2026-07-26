"""
Java Statement Emitter.

Purpose:
    Translate individual IR instructions into executable Java statement strings.

    This module is the authoritative translation layer between the IR instruction
    hierarchy and Java statement syntax.  Each ``emit_*`` function accepts a single
    IR instruction and returns one or more Java source lines (without indentation).

    Only :class:`~app.ir.instructions.IRMove` and
    :class:`~app.ir.instructions.IRDisplay` are translated in TASK-034.
    All other instruction types produce a ``// TODO:`` stub and a ``BE005``
    WARNING diagnostic so generation continues gracefully.

Design:
    Operand translation is shared between MOVE and DISPLAY via the private
    helper :func:`_translate_operand`, which converts an IR operand string
    into the equivalent Java expression:

    * Quoted string literals (``"..."`` in the IR) → emitted as-is.
    * Pure numeric strings → emitted as-is.
    * Otherwise → treated as COBOL identifier, converted to lowerCamelCase
      via :func:`~app.backend.java.naming.to_java_field_name`.

Responsibilities:
    - :func:`emit_statement` — dispatcher: routes an ``IRInstruction`` to the
      correct ``emit_*`` function.
    - :func:`emit_move` — MOVE → Java assignment.
    - :func:`emit_display` — DISPLAY → ``System.out.println()``.
    - Produce :class:`~app.backend.java.generator.BackendDiagnostic` records
      for unsupported instructions or missing operands.

Non-responsibilities:
    - Arithmetic translation (deferred).
    - Control-flow translation (deferred).
    - CALL translation (deferred).
    - Field declaration generation (:mod:`app.backend.java.field_model`).
    - Indentation management (handled by the caller).

Dependencies:
    - :mod:`app.ir.instructions` — ``IRInstruction``, ``IRMove``, ``IRDisplay``.
    - :mod:`app.backend.java.naming` — :func:`to_java_field_name`.
    - :mod:`app.backend.java.generator` — ``BackendDiagnostic``, ``BackendSeverity``.

Examples:
    Translating a DISPLAY instruction::

        from app.ir.instructions import IRDisplay, IRMove
        from app.backend.java.statement_emitter import emit_statement

        diags = []
        stmts, diags = emit_statement(IRDisplay(operand='"HELLO"'), diags)
        # stmts == ['System.out.println("HELLO");']

        stmts2, diags = emit_statement(IRMove(result="WS-COUNT", source="1"), diags)
        # stmts2 == ['wsCount = 1;']

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re

from app.backend.java.generator import BackendDiagnostic, BackendSeverity
from app.backend.java.naming import to_java_field_name
from app.ir.instructions import IRDisplay, IRInstruction, IRMove

__all__ = [
    "emit_display",
    "emit_move",
    "emit_statement",
]


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def emit_statement(
    instruction: IRInstruction,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate *instruction* into one or more Java statement strings.

    Supported instruction types:

    * :class:`~app.ir.instructions.IRMove`    → Java assignment.
    * :class:`~app.ir.instructions.IRDisplay` → ``System.out.println()``.

    All other instructions produce a ``// TODO: <type>`` comment and a
    ``BE005`` WARNING so that generation continues rather than failing.

    Args:
        instruction:
            The IR instruction to lower.
        diagnostics:
            Mutable list; backend diagnostics are appended here.

    Returns:
        A list of Java statement strings (no leading indentation).  May be
        empty if the instruction produces nothing (e.g. a void no-op).
    """
    if isinstance(instruction, IRMove):
        return emit_move(instruction, diagnostics)

    if isinstance(instruction, IRDisplay):
        return emit_display(instruction, diagnostics)

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
# Shared operand translator
# ---------------------------------------------------------------------------


def _translate_operand(operand: str) -> str:
    """
    Convert an IR operand string into a Java expression string.

    Translation rules (applied in order):

    1. **Quoted string literal** — operand starts and ends with ``"``:
       returned unchanged (e.g. ``'"HELLO"'`` → ``'"HELLO"'``).
    2. **Numeric literal** — operand matches ``[-+]?[0-9]+(\\.?[0-9]*)``:
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
