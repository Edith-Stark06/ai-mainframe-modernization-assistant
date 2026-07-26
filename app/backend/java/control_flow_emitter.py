"""
Java Control Flow Emitter.

Purpose:
    Translate structured control-flow IR instructions (:class:`~app.ir.instructions.IRIf`,
    :class:`~app.ir.instructions.IRElse`, :class:`~app.ir.instructions.IREndIf`) into
    Java conditional-block strings.

    This module is the authoritative translation layer for structured conditionals.
    Each public ``emit_*`` function accepts a single IR instruction (or no instruction
    for :func:`emit_else` and :func:`emit_end_if`), a nesting *depth* integer, and
    the shared diagnostics list.  It returns a list of Java source lines **without**
    the base 8-space ``main()`` indent (that is applied by the caller via
    :func:`~app.backend.java.generator._render_class`).

Design — depth-based indentation
    The *depth* argument represents the nesting level of the **header line** (the
    ``if``/``} else {``/``}`` token), not the body.  A ``depth`` of 0 means the
    conditional is directly inside ``main()``; a ``depth`` of 1 means it is nested
    inside another conditional.  Each nesting level adds 4 spaces of prefix
    (``"    " * depth``).

    Body statements (produced by :mod:`app.backend.java.statement_emitter`) receive
    their own depth prefix from :func:`~app.backend.java.generator._collect_statements`,
    which tracks the current depth and applies ``"    " * depth`` to every
    non-control-flow statement string.

Supported comparison operators
    ``==``, ``!=``, ``>``, ``>=``, ``<``, ``<=``

    Any other operator string produces a ``BE007`` WARNING diagnostic and returns an
    empty list (the IF block is skipped).

Condition translation
    Both operands (``left`` and ``right`` of :class:`~app.ir.instructions.IRIf`) go
    through :func:`~app.backend.java.statement_emitter._translate_operand`, which
    applies the standard operand-translation rules:

    1. Quoted strings  → emitted as-is.
    2. Numeric literals → emitted as-is.
    3. COBOL identifiers → lowerCamelCase via
       :func:`~app.backend.java.naming.to_java_field_name`.

Responsibilities:
    - :func:`emit_if`     — translate :class:`IRIf` into ``if (<cond>) {``.
    - :func:`emit_else`   — emit ``} else {`` at the correct depth.
    - :func:`emit_end_if` — emit ``}`` at the correct depth.
    - :func:`_build_condition` — validate and translate the condition triple.
    - Produce :class:`~app.backend.java.generator.BackendDiagnostic` records
      (code ``BE007``) for unsupported operators and empty operands.

Non-responsibilities:
    - Depth tracking (managed by :func:`~app.backend.java.generator._collect_statements`).
    - Statement indentation for body instructions (managed by the same caller).
    - PERFORM / EVALUATE / CALL translation (deferred).
    - File I/O translation (deferred).

Dependencies:
    - :mod:`app.ir.instructions`         — ``IRIf``.
    - :mod:`app.backend.java.generator`  — ``BackendDiagnostic``, ``BackendSeverity``.
    - :mod:`app.backend.java.statement_emitter` — :func:`_translate_operand`.

Examples:
    Translating a simple IF at depth 0::

        from app.ir.instructions import IRIf
        from app.backend.java.control_flow_emitter import emit_if, emit_else, emit_end_if

        diags = []
        instr = IRIf(left="WS-COUNT", operator=">", right="0")
        emit_if(instr, 0, diags)
        # ['if (wsCount > 0) {']

        emit_else(0, diags)
        # ['} else {']

        emit_end_if(0, diags)
        # ['}']

    Translating a nested IF at depth 1::

        emit_if(IRIf(left="WS-A", operator="==", right="WS-B"), 1, diags)
        # ['    if (wsA == wsB) {']

        emit_end_if(1, diags)
        # ['    }']

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.backend.java.generator import BackendDiagnostic, BackendSeverity

if TYPE_CHECKING:
    from app.ir.instructions import IRIf

__all__ = [
    "SUPPORTED_OPERATORS",
    "emit_else",
    "emit_end_if",
    "emit_if",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_OPERATORS: frozenset[str] = frozenset({"==", "!=", ">", ">=", "<", "<="})
"""The set of comparison operator strings accepted by :func:`emit_if`."""


# ---------------------------------------------------------------------------
# emit_if — IRIf → Java ``if (<condition>) {``
# ---------------------------------------------------------------------------


def emit_if(
    instruction: IRIf,
    depth: int,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRIf` into a Java
    ``if (<condition>) {`` header line.

    The prefix ``"    " * depth`` is prepended to position the header at the
    correct nesting level within ``main()``.

    Rules:
        - ``IF WS-COUNT > 0``      → ``if (wsCount > 0) {``   (depth 0)
        - ``IF WS-A == WS-B``      → ``if (wsA == wsB) {``    (depth 0)
        - ``IF WS-X != 0``         → ``    if (wsX != 0) {``  (depth 1)

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRIf` to translate.
        depth:
            Current nesting depth of this header line (0 = flat inside main).
        diagnostics:
            Mutable list; ``BE007`` diagnostics appended on error.

    Returns:
        A list containing exactly one ``if (<cond>) {`` string, or an empty
        list when the condition cannot be translated.
    """
    condition = _build_condition(
        instruction.left, instruction.operator, instruction.right, diagnostics
    )
    if condition is None:
        return []

    prefix = "    " * depth
    return [f"{prefix}if ({condition}) {{"]


# ---------------------------------------------------------------------------
# emit_else — emit ``} else {``
# ---------------------------------------------------------------------------


def emit_else(
    depth: int,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Emit a Java ``} else {`` transition line at the given *depth*.

    This function does not validate whether an open IF block exists;
    that responsibility belongs to :func:`~app.backend.java.generator._collect_statements`.

    Args:
        depth:
            The nesting depth of the **if-header** (same level as the ``else``
            keyword — one less than the body depth).
        diagnostics:
            Mutable list; currently unused but kept for API symmetry.

    Returns:
        A list containing exactly one ``} else {`` string with the appropriate
        depth prefix.
    """
    prefix = "    " * depth
    return [f"{prefix}}} else {{"]


# ---------------------------------------------------------------------------
# emit_end_if — emit ``}``
# ---------------------------------------------------------------------------


def emit_end_if(
    depth: int,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Emit a Java closing brace ``}`` for an IF or ELSE block at the given *depth*.

    Args:
        depth:
            The nesting depth of the **if-header** (same level as the closing
            brace — one less than the body depth).
        diagnostics:
            Mutable list; currently unused but kept for API symmetry.

    Returns:
        A list containing exactly one ``}`` string with the appropriate depth prefix.
    """
    prefix = "    " * depth
    return [f"{prefix}}}"]


# ---------------------------------------------------------------------------
# Internal condition builder
# ---------------------------------------------------------------------------


def _build_condition(
    left: str,
    operator: str,
    right: str,
    diagnostics: list[BackendDiagnostic],
) -> str | None:
    """
    Validate and translate a condition triple into a Java expression string.

    Validation rules (each violation appends a ``BE007`` WARNING and returns
    ``None``):

    1. ``left`` must not be empty.
    2. ``operator`` must be one of :data:`SUPPORTED_OPERATORS`.
    3. ``right`` must not be empty.

    If all checks pass, both operands are translated via
    :func:`~app.backend.java.statement_emitter._translate_operand` and the
    result is assembled as ``"<java_left> <operator> <java_right>"``.

    Args:
        left:
            Left-hand IR operand string.
        operator:
            Comparison operator string (e.g. ``">"``, ``"==\"``).
        right:
            Right-hand IR operand string.
        diagnostics:
            Mutable list; ``BE007`` diagnostics appended on error.

    Returns:
        A Java condition expression string such as ``"wsCount > 0"`` or
        ``None`` when validation fails.
    """
    # Import here to avoid circular imports at module level.
    from app.backend.java.statement_emitter import _translate_operand

    if not left:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRIf has empty left operand; skipping IF block.",
                code="BE007",
            )
        )
        return None

    if operator not in SUPPORTED_OPERATORS:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"IRIf has unsupported operator '{operator}'; "
                    f"supported operators are {sorted(SUPPORTED_OPERATORS)}. "
                    "Skipping IF block."
                ),
                code="BE007",
            )
        )
        return None

    if not right:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRIf has empty right operand; skipping IF block.",
                code="BE007",
            )
        )
        return None

    java_left = _translate_operand(left)
    java_right = _translate_operand(right)
    return f"{java_left} {operator} {java_right}"
