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

    Post-#111 review fix adds translation for
    :class:`~app.ir.instructions.IRReturn` (COBOL ``STOP RUN`` / ``GOBACK``,
    task #109) → a bare ``return;`` — see :func:`emit_return`.

    All other instruction types produce a ``// TODO:`` stub and a ``BE005``
    WARNING diagnostic so generation continues gracefully.

    Task #stage31 adds COBOL DISPLAY formatting for unformatted PICTURE
    fields: :func:`emit_display` zero-pads an unsigned ``PIC 9(n)``/
    ``PIC 9(n)V9(m)`` operand to its declared digit width (never printing the
    assumed ``V``) and space-pads a ``PIC X(n)`` operand to its declared
    length, when an optional :class:`~app.backend.java.condition_context.ConditionContext`
    carrying the operand's :class:`~app.backend.java.field_model.JavaField`
    is supplied.  See :func:`emit_display` and :func:`_format_display_operand`
    for the exact scope (signed items, edited PICTUREs and group ``DISPLAY``
    are deliberately left unformatted).

    Task #stage42 gives :func:`emit_compute` the same optional
    ``ConditionContext`` parameter: when the ``COMPUTE`` target's declared
    Java type is ``int``/``int[]`` and the expression tree contains any
    ``double``-typed operand, the rendered expression is wrapped in an
    explicit ``(int)`` cast — Java, unlike COBOL, has no implicit
    ``double`` -> ``int`` narrowing conversion on assignment. See
    :func:`emit_compute` and :func:`_expression_has_double_operand`.

Design:
    Operand translation is shared across all emitters via the private helper
    :func:`_translate_operand`, which converts an IR operand string into the
    equivalent Java expression:

    * Quoted string literals (``"..."`` in the IR) → emitted as-is.
    * Pure numeric strings (integer or decimal, optional sign) → emitted as-is.
    * Otherwise → treated as COBOL identifier, converted to lowerCamelCase via
      :func:`~app.backend.java.naming.to_java_field_name`.

    Task #stage33 adds Java-array lowering for a structured table subscript
    (task #stage32's ``IRSubscript``, carried by ``IRMove``/``IRAdd``/
    ``IRSubtract``/``IRMultiply``/``IRDivide``/``IRDisplay``/``IRIf``/
    ``IRConditionTerm``). Every one of those instruction types' emitter —
    including :func:`~app.backend.java.control_flow_emitter.emit_if` via
    :func:`~app.backend.java.control_flow_emitter._build_condition`, which
    imports from this module exactly as it already did — reaches Java array
    indexing through exactly two functions, never by composing ``[...]``
    itself:

    * :func:`_translate_subscript_index` — the *only* place COBOL's 1-based
      subscript becomes a 0-based Java index: a literal subscript ``"2"``
      becomes ``"1"``; an identifier subscript ``"WS-I"`` becomes
      ``"wsI - 1"`` (via the same :func:`~app.backend.java.naming.to_java_field_name`
      every other identifier goes through — no second naming algorithm).
    * :func:`_render_reference` — renders a base COBOL name as a plain Java
      field (``"wsItem"``) or, when given a non-empty subscript tuple, as an
      indexed array reference (``"wsItem[1]"``). :func:`_translate_operand`
      gained an optional *subscripts* parameter and delegates its own
      identifier branch (rule 4) to this same function, so a subscripted
      *value* operand (MOVE source, arithmetic ``left``, a condition
      operand, a DISPLAY operand) and a subscripted *target* (MOVE/
      arithmetic ``result``, rendered directly via :func:`_render_reference`
      since a target is never a literal) share one implementation.

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
    - :func:`emit_return`     — STOP RUN / GOBACK (``IRReturn``) → ``return;``.
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

from app.backend.java.condition_context import (
    COBOL_ACCEPT,
    ConditionContext,
    operand_java_type,
)
from app.backend.java.control_flow_emitter import (
    emit_else,
    emit_end_if,
    emit_end_perform,
    emit_if,
    emit_perform_until,
    emit_perform_varying,
)
from app.backend.java.generator import BackendDiagnostic, BackendSeverity
from app.backend.java.naming import to_java_field_name
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRArithmeticExpression,
    IRCall,
    IRCompute,
    IRDisplay,
    IRDivide,
    IRElse,
    IREndIf,
    IREndPerform,
    IRIf,
    IRInstruction,
    IRMove,
    IRMultiply,
    IROperandExpression,
    IRPerformUntil,
    IRPerformVarying,
    IRReturn,
    IRSubscript,
    IRSubtract,
)

__all__ = [
    "emit_add",
    "emit_call",
    "emit_compute",
    "emit_display",
    "emit_divide",
    "emit_else",
    "emit_end_if",
    "emit_end_perform",
    "emit_if",
    "emit_move",
    "emit_multiply",
    "emit_perform_until",
    "emit_perform_varying",
    "emit_return",
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
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate *instruction* into one or more Java statement strings.

    Supported instruction types:

    * :class:`~app.ir.instructions.IRMove`     → Java assignment (``=``).
    * :class:`~app.ir.instructions.IRDisplay`  → ``System.out.println()``.
    * :class:`~app.ir.instructions.IRAccept`   → assignment from a console-read helper.
    * :class:`~app.ir.instructions.IRAdd`      → ``+=`` compound assignment.
    * :class:`~app.ir.instructions.IRSubtract` → ``-=`` compound assignment.
    * :class:`~app.ir.instructions.IRMultiply` → ``*=`` compound assignment.
    * :class:`~app.ir.instructions.IRDivide`   → ``/=`` compound assignment.
    * :class:`~app.ir.instructions.IRCompute` (task #stage35) → a fresh Java
      assignment of the translated expression (``result = <expr>;``), not a
      compound assignment.
    * :class:`~app.ir.instructions.IRCall`     → ``target(args);`` (or ``result = target(args);``).
    * :class:`~app.ir.instructions.IRReturn`   → ``return;``.
    * :class:`~app.ir.instructions.IRIf`       → ``if (<cond>) {`` (at *depth*).
    * :class:`~app.ir.instructions.IRElse`     → ``} else {`` (at *depth*).
    * :class:`~app.ir.instructions.IREndIf`    → ``}`` (at *depth*).
    * :class:`~app.ir.instructions.IRPerformUntil` → ``while (!(<cond>)) {`` (at *depth*).
    * :class:`~app.ir.instructions.IRPerformVarying` (task #stage34) →
      ``for (<init>; <continue>; <step>) {`` (at *depth*).
    * :class:`~app.ir.instructions.IREndPerform` → ``}`` (at *depth*, closes
      either an ``IRPerformUntil`` or an ``IRPerformVarying``).

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
        context:
            Optional :class:`~app.backend.java.condition_context.ConditionContext`.
            Passed through to :func:`emit_display` (task #stage31), where it
            supplies the declared PICTURE width/scale of a DISPLAY'd field
            for zero-/space-padding, and to :func:`emit_compute` (task
            #stage42), where it supplies the target's declared Java type to
            decide whether a ``double``-into-``int`` narrowing cast is
            needed.  Not otherwise consulted by this dispatcher: an
            ``IRIf``/``IRPerformUntil`` reached here (a direct call, not the
            depth-aware path in
            :func:`~app.backend.java.generator._collect_statements`) is
            translated exactly as before, with no condition context.
            ``None`` (the default) reproduces the exact pre-#stage31
            behavior for every instruction type.

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
        emit_perform_varying as _emit_perform_varying,
    )

    if isinstance(instruction, IRMove):
        return emit_move(instruction, diagnostics)

    if isinstance(instruction, IRDisplay):
        return emit_display(instruction, diagnostics, context)

    if isinstance(instruction, IRAccept):
        return emit_accept(instruction, diagnostics, context)

    if isinstance(instruction, IRAdd):
        return emit_add(instruction, diagnostics)

    if isinstance(instruction, IRSubtract):
        return emit_subtract(instruction, diagnostics)

    if isinstance(instruction, IRMultiply):
        return emit_multiply(instruction, diagnostics)

    if isinstance(instruction, IRDivide):
        return emit_divide(instruction, diagnostics)

    if isinstance(instruction, IRCompute):
        return emit_compute(instruction, diagnostics, context)

    if isinstance(instruction, IRCall):
        return emit_call(instruction, diagnostics)

    if isinstance(instruction, IRReturn):
        return emit_return(instruction, diagnostics)

    if isinstance(instruction, IRIf):
        return _emit_if(instruction, depth, diagnostics)

    if isinstance(instruction, IRElse):
        return _emit_else(depth, diagnostics)

    if isinstance(instruction, IREndIf):
        return _emit_end_if(depth, diagnostics)

    if isinstance(instruction, IRPerformUntil):
        return _emit_perform_until(instruction, depth, diagnostics)

    if isinstance(instruction, IRPerformVarying):
        return _emit_perform_varying(instruction, depth, diagnostics)

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
        - ``MOVE 123 -> WS-ITEM(2)``      → ``wsItem[1] = 123;`` (task
          #stage33 — ``instruction.result_subscript``)
        - ``MOVE WS-ITEM(WS-I) -> WS-TOTAL`` → ``wsTotal = wsItem[wsI - 1];``
          (``instruction.source_subscript``)

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

    java_target = _render_reference(target, instruction.result_subscript)
    java_source = _translate_operand(source, instruction.source_subscript)

    return [f"{java_target} = {java_source};"]


# ---------------------------------------------------------------------------
# DISPLAY → System.out.println()
# ---------------------------------------------------------------------------


def emit_display(
    instruction: IRDisplay,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRDisplay` into a Java
    ``System.out.println()`` call.

    Rules:
        - ``DISPLAY "HELLO"``    → ``System.out.println("HELLO");``
        - ``DISPLAY WS-NAME``    → ``System.out.println(wsName);``
        - ``DISPLAY 42``         → ``System.out.println(42);``
        - ``DISPLAY WS-ITEM(2)``    → ``System.out.println(wsItem[1]);``
          (task #stage33 — ``instruction.operand_subscript``)
        - ``DISPLAY WS-ITEM(WS-I)`` → ``System.out.println(wsItem[wsI - 1]);``

    With *context* supplied, an operand that is a plain field reference is
    additionally formatted the way COBOL DISPLAY implicitly formats it
    (task #stage31) -- see :func:`_format_display_operand` for the exact,
    deliberately narrow scope. Without *context* (the default), this
    function's behavior is byte-for-byte what it was before #stage31.

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRDisplay` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.
        context:
            Optional :class:`~app.backend.java.condition_context.ConditionContext`
            carrying the declared :class:`~app.backend.java.field_model.JavaField`
            of every field (``digits``/``decimal_places``/``signed``/
            ``length``). ``None`` disables DISPLAY formatting entirely.

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

    if len(instruction.operands) > 1:
        return _emit_multi_operand_display(instruction, diagnostics, context)

    java_operand = _translate_operand(operand, instruction.operand_subscript)
    java_operand = _format_display_operand(
        operand, java_operand, context, bool(instruction.operand_subscript)
    )
    return [f"System.out.println({java_operand});"]


def emit_accept(
    instruction: IRAccept,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRAccept` into an assignment
    from a console-read helper chosen by the target's declared Java type.

    ``String`` targets receive the raw line, ``int`` and ``double``
    targets the parsed number (zero when the text is not numeric). The
    helpers are emitted once per class by the generator (see
    :data:`~app.backend.java.condition_context.COBOL_ACCEPT_HELPER`).

    An empty target raises ``BE004``; a target whose Java type is unknown
    or is not one of the three above raises ``BE016``. Either way the
    statement is skipped rather than guessed.

    Args:
        instruction: The ``ACCEPT`` to lower.
        diagnostics: Mutable list; diagnostics are appended here.
        context: Supplies the target's declared Java type. Without it the
            type is unknown and the statement is skipped with ``BE016``.

    Returns:
        A one-element list holding the assignment, or ``[]`` when skipped.
    """
    target = instruction.result.strip()
    if not target:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRAccept has empty target; skipping.",
                code="BE004",
            )
        )
        return []

    java_target = _translate_operand(target)
    java_type = context.field_types.get(java_target) if context else None
    helper = {
        "String": f"{COBOL_ACCEPT}Line",
        "int": f"{COBOL_ACCEPT}Int",
        "double": f"{COBOL_ACCEPT}Double",
    }.get(java_type or "")
    if helper is None:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"ACCEPT target {target!r} has Java type {java_type!r}, "
                    "which has no console-read mapping; statement skipped."
                ),
                code="BE016",
            )
        )
        return []
    return [f"{java_target} = {helper}();"]


def _emit_multi_operand_display(
    instruction: IRDisplay,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None,
) -> list[str]:
    """
    Translate ``DISPLAY a b c`` into one ``System.out.println(a + b + c)``.

    COBOL writes the operands' display forms back to back with no
    separator, so each operand goes through the same translation and
    PICTURE-aware formatting a single-operand DISPLAY gets, and the
    results are concatenated. The expression starts from a String
    (``"" + ...`` unless the first piece already is a string literal) so
    Java performs string concatenation even when the first two operands
    are numeric -- ``wsA + wsB`` alone would add them.

    A subscripted operand inside a multi-operand list is carried by the
    parser as flattened text, which cannot be lowered to an array index
    here. Rather than emit Java that does not compile, the statement is
    skipped with a ``BE015`` WARNING.
    """
    pieces: list[str] = []
    for operand in instruction.operands:
        if "(" in operand:
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=(
                        f"DISPLAY operand {operand!r} is a subscripted "
                        "reference inside a multi-operand DISPLAY, which is "
                        "not supported; statement skipped."
                    ),
                    code="BE015",
                )
            )
            return []
        java_operand = _translate_operand(operand)
        pieces.append(_format_display_operand(operand, java_operand, context))

    expression = " + ".join(pieces)
    if not pieces[0].startswith('"'):
        expression = '"" + ' + expression
    return [f"System.out.println({expression});"]


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

    # task #stage33: `result` mirrors the IR's own `right` operand for all
    # four arithmetic instructions (Stage 32 populated `result_subscript`
    # and `right_subscript` identically; the emitter has never read `right`
    # itself, only `result`/`left`, so `result_subscript` is what belongs
    # here — see this module's docstring and app/ir/instructions.py).
    java_result = _render_reference(result, instruction.result_subscript)
    java_left = _translate_operand(left, instruction.left_subscript)

    return [f"{java_result} {operator} {java_left};"]


# ---------------------------------------------------------------------------
# COMPUTE → Java assignment of a translated expression (task #stage35)
# ---------------------------------------------------------------------------

#: Arithmetic operator precedence, matching
#: :data:`app.ir.instructions._ARITHMETIC_PRECEDENCE` exactly (COBOL's and
#: Java's precedence for ``+ - * /`` are identical) -- kept as its own
#: private copy here rather than imported, the same way this module's own
#: :func:`_render_operand`-equivalent (:func:`_render_reference`/
#: :func:`_translate_operand`) is already an independent, Java-specific
#: sibling of :mod:`app.ir.instructions`'s debug-text
#: ``_render_operand``, not a shared/parametrized implementation.
_ARITHMETIC_PRECEDENCE: dict[str, int] = {"+": 1, "-": 1, "*": 2, "/": 2}


def _translate_expression(
    expression: IRArithmeticExpression, parent_precedence: int = 0
) -> str:
    """
    Render an :data:`~app.ir.instructions.IRArithmeticExpression` tree into
    a Java expression string (task #stage35).

    A leaf operand goes through :func:`_translate_operand` exactly the way
    every other arithmetic instruction's operand already does — literal/
    identifier classification, lowerCamelCase field naming, and (task
    #stage32/33) a subscripted leaf's 0-based Java array index, all via the
    same single conversion point every other emitter uses. A
    :class:`~app.ir.instructions.IRBinaryExpression` node recurses on both
    sides and inserts parentheses only where COBOL's (and Java's — the two
    languages' precedence for ``+ - * /`` is identical, so no translation
    between them is needed) evaluation order would otherwise change; see
    :func:`app.ir.instructions.render_arithmetic_expression`'s docstring
    for the precedence-climbing algorithm this mirrors.

    Args:
        expression: The expression tree to render.
        parent_precedence: The precedence level of the context this
            expression is being printed into; ``0`` for a top-level
            expression, which is never parenthesized.

    Returns:
        A Java expression string, e.g. ``"b * (c + d)"``.

    Examples:
        >>> _translate_expression(
        ...     IRBinaryExpression(
        ...         operator="*",
        ...         left=IROperandExpression(value="B"),
        ...         right=IRBinaryExpression(
        ...             operator="+",
        ...             left=IROperandExpression(value="C"),
        ...             right=IROperandExpression(value="D"),
        ...         ),
        ...     )
        ... )
        'b * (c + d)'
    """
    if isinstance(expression, IROperandExpression):
        return _translate_operand(expression.value, expression.subscript)

    precedence = _ARITHMETIC_PRECEDENCE[expression.operator]
    left_text = _translate_expression(expression.left, precedence)
    right_text = _translate_expression(expression.right, precedence + 1)
    text = f"{left_text} {expression.operator} {right_text}"
    if precedence < parent_precedence:
        return f"({text})"
    return text


def _expression_has_double_operand(
    expression: IRArithmeticExpression, context: ConditionContext
) -> bool:
    """
    ``True`` if any leaf operand of *expression* is Java-typed ``double``
    (task #stage42).

    Mirrors Java's own numeric-promotion rule for ``+``/``-``/``*``/``/``:
    an arithmetic expression is ``double``-valued if *any* operand
    anywhere in its tree is, regardless of where in the tree it sits —
    so this recurses into both sides of every
    :class:`~app.ir.instructions.IRBinaryExpression` node rather than
    only checking the top level.

    A leaf that is a subscripted ``OCCURS`` array element (task
    #stage32/33) is checked against ``"double[]"`` too:
    :attr:`~app.backend.java.field_model.JavaField.java_type` for an
    array field is the *array's* type (``"double[]"``), never the bare
    element type, but a subscripted reference inside an arithmetic
    expression always denotes one scalar element (Java has no arithmetic
    operators on array references), so ``operand_java_type``'s
    ``"double[]"`` answer for that leaf means the same thing a plain
    ``"double"`` field would.

    Args:
        expression: The expression tree to inspect.
        context: What is known about the operands' declared types.

    Returns:
        Whether Java would infer this expression's type as ``double``.
    """
    if isinstance(expression, IROperandExpression):
        return operand_java_type(expression.value, context) in (
            "double",
            "double[]",
        )
    return _expression_has_double_operand(
        expression.left, context
    ) or _expression_has_double_operand(expression.right, context)


def emit_compute(
    instruction: IRCompute,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRCompute` into a Java
    assignment (task #stage35).

    Unlike :func:`emit_add` and its siblings — a compound assignment onto
    an existing value, because that is all ADD/SUBTRACT/MULTIPLY/DIVIDE's
    COBOL grammar ever expresses — COMPUTE assigns a freshly evaluated
    expression, so this always emits a plain ``=`` assignment, never a
    compound operator.

    Rules:
        - ``COMPUTE A = B + C``            → ``a = b + c;``
        - ``COMPUTE A = B * (C + D)``      → ``a = b * (c + d);``
        - ``COMPUTE A(WS-I) = B(WS-I) * C`` → ``a[wsI - 1] = b[wsI - 1] * c;``
          (task #stage32/33 — ``instruction.result_subscript`` and each
          leaf operand's own subscript, translated by the same
          :func:`_translate_subscript_index` every other emitter uses)
        - ``COMPUTE A = B * C`` where ``A`` is ``int`` and ``B``/``C``
          make the expression ``double``-valued → ``a = (int) (b * c);``
          (task #stage42 — see below)

    COBOL allows a ``COMPUTE`` with a decimal-valued expression to store
    into an integer-PICTURE target (implicitly truncating, unless
    ``ROUNDED`` is specified — this backend does not model ``ROUNDED``,
    an unevidenced, separate, out-of-scope gap). Java has no implicit
    narrowing conversion for ``double`` → ``int`` in an assignment, so
    the un-cast translation (still emitted when *context* is ``None``, or
    the target's type is unknown to it) fails to compile with
    "incompatible types: possible lossy conversion from double to int" —
    confirmed directly against the real corpus source that surfaced this
    (``data/sources/phase6-v2/inventory_reorder.cbl``,
    ``COMPUTE REORDER-POINT-QTY = (AVG-DAILY-DEMAND * SUPPLIER-LEAD-DAYS
    * SEASONALITY-INDEX) + SAFETY-STOCK-LEVEL``, an integer target with
    two ``V99`` decimal operands in the expression). An explicit
    ``(int)`` cast reproduces COBOL's own truncate-on-store behavior
    (Java's numeric cast truncates toward zero, matching COBOL's default
    un-``ROUNDED`` truncation for this domain's non-negative quantities).

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRCompute` to lower.
        diagnostics:
            Mutable list; diagnostics appended on error.
        context:
            Optional :class:`~app.backend.java.condition_context.ConditionContext`
            carrying every declared field's Java type, used to detect the
            ``double``-into-``int`` narrowing case above. Without it, the
            expression is translated exactly as before, with no cast --
            matching every other optional-context translation in this
            backend.

    Returns:
        A list containing exactly one Java assignment string, or an empty
        list when the instruction is malformed.
    """
    target = instruction.result

    if not target:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRCompute has empty result (target); skipping.",
                code="BE006",
            )
        )
        return []

    if instruction.expression is None:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=f"IRCompute to '{target}' has no expression; skipping.",
                code="BE006",
            )
        )
        return []

    java_target = _render_reference(target, instruction.result_subscript)
    java_expression = _translate_expression(instruction.expression)

    if (
        context is not None
        # "int[]" (task #stage33's OCCURS array element type) needs the
        # cast exactly like a scalar "int" field does -- a subscripted
        # COMPUTE target assigns one element, never the whole array, and
        # JavaField.java_type carries the trailing "[]" regardless of
        # whether a particular occurrence is subscripted.
        and context.field_types.get(to_java_field_name(target)) in ("int", "int[]")
        and _expression_has_double_operand(instruction.expression, context)
    ):
        java_expression = f"(int) ({java_expression})"

    return [f"{java_target} = {java_expression};"]


# ---------------------------------------------------------------------------
# Shared operand translator
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CALL → Java method invocation
# ---------------------------------------------------------------------------


def emit_call(
    instruction: IRCall,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRCall` into a Java method invocation.

    The target name is converted to lowerCamelCase via :func:`to_java_field_name`.
    Each argument is translated via :func:`_translate_operand`.

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRCall` to translate.
        diagnostics:
            Mutable list; diagnostics appended on error.

    Returns:
        A list containing exactly one Java statement string.
    """
    target = instruction.target
    if not target:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRCall has empty target; skipping.",
                code="BE008",
            )
        )
        return []

    # Strip quotes if they were included natively (COBOL often has CALL "NAME")
    if target.startswith('"') and target.endswith('"') and len(target) >= 2:
        target = target[1:-1]
    elif target.startswith("'") and target.endswith("'") and len(target) >= 2:
        target = target[1:-1]

    java_target = to_java_field_name(target)

    # Translate all arguments
    translated_args = []
    for arg in instruction.args:
        if not arg:
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=f"IRCall to '{target}' has an empty argument; skipping.",
                    code="BE008",
                )
            )
            return []
        translated_args.append(_translate_operand(arg))

    args_str = ", ".join(translated_args)

    if instruction.result:
        java_result = to_java_field_name(instruction.result)
        return [f"{java_result} = {java_target}({args_str});"]

    return [f"{java_target}({args_str});"]


# ---------------------------------------------------------------------------
# IRReturn → Java return statement
# ---------------------------------------------------------------------------


def emit_return(
    instruction: IRReturn,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRReturn` into a Java
    ``return;`` statement.

    :class:`~app.ir.instructions.IRReturn` corresponds to a COBOL
    ``STOP RUN`` or ``GOBACK`` statement (distinguished, where needed by
    other passes, via ``instruction.comment``). Both currently lower to
    the same bare ``return;`` here: the generator emits exactly one
    non-stub method — the instance ``run()`` method invoked from
    ``main`` (see :func:`~app.backend.java.generator._render_class`) —
    since paragraph bodies are not split into separate Java methods
    (:mod:`app.ir.builder`'s documented architectural decision). With
    only one real method to return from, a program-terminating
    ``STOP RUN`` and a caller-returning ``GOBACK`` have no distinguishable
    Java rendering today; both simply end the enclosing ``run()`` call.

    ``run()`` is declared ``void``. ``instruction.operand`` (a value to
    return) can therefore never be honoured in valid Java — the current
    producers (``build_stop_run_instruction``/``build_goback_instruction``
    in :mod:`app.ir.builder`) always leave it empty, but a ``BE010``
    WARNING is raised rather than silently emitting ``return <value>;``
    inside a void method if a future producer ever sets it.

    Rules:
        - ``STOP RUN`` / ``GOBACK`` (``operand == ""``) → ``return;``
        - Non-empty ``operand`` → ``return;`` plus a ``BE010`` WARNING
          noting the value could not be returned from a void method.

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRReturn` to lower.
        diagnostics:
            Mutable list; a ``BE010`` WARNING is appended if ``operand``
            is non-empty.

    Returns:
        A list containing exactly one ``"return;"`` string.
    """
    if instruction.operand:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"IRReturn carries operand '{instruction.operand}', but "
                    "the generated run() method is void and cannot return a "
                    "value; operand is ignored."
                ),
                code="BE010",
            )
        )
    return ["return;"]


def _escape_java_string_content(text: str) -> str:
    r"""
    Escape *text* for safe embedding inside a Java ``"..."`` string literal.

    Only backslash and double-quote need escaping: the lexer that produced
    every COBOL string-literal token forbids an embedded newline or carriage
    return (``LexerError: unterminated string literal``), so *text* is always
    a single line, and it can never contain the literal's own delimiter
    (single quote) since the lexer stops scanning at the first one. Anything
    else -- including non-ASCII characters -- is valid, unescaped Java source
    text and is passed through unchanged.

    Examples:
        >>> _escape_java_string_content("PLAIN")
        'PLAIN'
        >>> _escape_java_string_content('HAS "QUOTES"')
        'HAS \\"QUOTES\\"'
        >>> _escape_java_string_content("BACK\\SLASH")
        'BACK\\\\SLASH'
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _translate_subscript_index(subscript: IRSubscript) -> str:
    """
    Lower one structured, 1-based COBOL subscript (task #stage32's
    ``IRSubscript``) into its 0-based Java array-index expression.

    This is the **only** place the ``-1`` adjustment happens anywhere in the
    Java backend (task #stage33) -- never in the AST, never in the IR (both
    deliberately preserve COBOL's own 1-based meaning), and never
    recomputed independently by any individual emitter.

    Args:
        subscript:
            A single ``IRSubscript`` — ``kind="literal"`` (a bare integer)
            or ``kind="identifier"`` (a data-name, already canonicalised by
            :meth:`~app.ir.builder.IRBuilder.build_subscripts` the same way
            any other operand is).

    Returns:
        A Java index expression string.

    Examples:
        >>> _translate_subscript_index(IRSubscript(kind="literal", value="2"))
        '1'
        >>> _translate_subscript_index(IRSubscript(kind="literal", value="1"))
        '0'
        >>> _translate_subscript_index(IRSubscript(kind="identifier", value="WS-I"))
        'wsI - 1'
        >>> _translate_subscript_index(
        ...     IRSubscript(kind="identifier", value="CURRENT-IDX")
        ... )
        'currentIdx - 1'
    """
    if subscript.kind == "literal":
        try:
            return str(int(subscript.value) - 1)
        except ValueError:
            # Defensive only: task #stage32's parser captures a literal
            # subscript from a NUMBER token exclusively, so a non-integer
            # literal value cannot occur in practice.
            return f"({subscript.value} - 1)"
    return f"{to_java_field_name(subscript.value)} - 1"


def _render_reference(name: str, subscripts: tuple[IRSubscript, ...] = ()) -> str:
    """
    Render a COBOL identifier reference as a Java expression.

    With no *subscripts*, this is exactly
    :func:`~app.backend.java.naming.to_java_field_name` — a plain field
    reference, byte-for-byte what every pre-#stage33 caller already
    produced. With one (task #stage32/#stage33 scope is single-dimension
    only), it is a Java array-indexed reference built from the **same**
    :func:`_translate_subscript_index` every other emitter uses — this
    function is the one place ``[...]`` is composed anywhere in the Java
    backend.

    Args:
        name:
            A COBOL identifier (e.g. ``"WS-ITEM"``).
        subscripts:
            Zero or one :class:`~app.ir.instructions.IRSubscript`. Empty by
            default so every existing call site is unaffected.

    Returns:
        ``"wsItem"`` (no subscripts) or ``"wsItem[1]"`` /
        ``"wsItem[wsI - 1]"`` (one subscript).

    Examples:
        >>> _render_reference("WS-ITEM")
        'wsItem'
        >>> _render_reference("WS-ITEM", (IRSubscript(kind="literal", value="2"),))
        'wsItem[1]'
        >>> _render_reference(
        ...     "WS-ITEM", (IRSubscript(kind="identifier", value="WS-I"),)
        ... )
        'wsItem[wsI - 1]'
    """
    java_name = to_java_field_name(name)
    if not subscripts:
        return java_name
    return f"{java_name}[{_translate_subscript_index(subscripts[0])}]"


def _translate_operand(operand: str, subscripts: tuple[IRSubscript, ...] = ()) -> str:
    """
    Convert an IR operand string into a Java expression string.

    Translation rules (applied in order):

    1. **Double-quoted string literal** — operand starts and ends with ``"``:
       returned unchanged (e.g. ``'"HELLO"'`` → ``'"HELLO"'``).
    2. **Single-quoted string literal** — operand starts and ends with ``'``:
       COBOL's own string-literal delimiter. Re-emitted as a Java
       double-quoted string literal with the same content, escaped via
       :func:`_escape_java_string_content` (e.g. ``"'Y'"`` → ``'"Y"'``).
       Without this rule the content was treated as rule 4's COBOL
       identifier and silently turned into an undeclared Java variable
       reference (``'Y'`` → ``y``) -- a ``javac`` compile failure, not a
       translation of the literal's value.
    3. **Numeric literal** — operand matches ``[-+]?[0-9]+(\\.?[0-9]*)``:\
       returned unchanged (e.g. ``'42'`` → ``'42'``).
    4. **Identifier** — everything else is treated as a COBOL name and
       rendered via :func:`_render_reference` (lowerCamelCase, plus a Java
       array index when *subscripts* is non-empty, task #stage33).

    Args:
        operand:
            An IR operand string such as ``'"HELLO"'``, ``"'Y'"``, ``'42'``,
            or ``'WS-GREETING'``.
        subscripts:
            Zero or one structured :class:`~app.ir.instructions.IRSubscript`
            (task #stage32) for *operand*, when it is a table reference.
            Empty by default; a literal/numeric *operand* can never carry
            one (COBOL cannot subscript a literal), so this only ever
            affects rule 4.

    Returns:
        A Java expression string ready for embedding in a statement.

    Examples:
        >>> _translate_operand('"HELLO"')
        '"HELLO"'
        >>> _translate_operand("'Y'")
        '"Y"'
        >>> _translate_operand('42')
        '42'
        >>> _translate_operand('WS-GREETING')
        'wsGreeting'
        >>> _translate_operand('WS-ITEM', (IRSubscript(kind="literal", value="2"),))
        'wsItem[1]'
    """
    # 1. Double-quoted string literal
    if operand.startswith('"') and operand.endswith('"') and len(operand) >= 2:
        return operand

    # 2. Single-quoted string literal (COBOL's own delimiter)
    if operand.startswith("'") and operand.endswith("'") and len(operand) >= 2:
        return f'"{_escape_java_string_content(operand[1:-1])}"'

    # 3. Numeric literal (integer or decimal, optional sign)
    if re.match(r"^[+-]?\d+(\.\d+)?$", operand):
        return operand

    # 4. COBOL identifier → lowerCamelCase, optionally array-indexed
    return _render_reference(operand, subscripts)


# ---------------------------------------------------------------------------
# DISPLAY formatting (task #stage31)
# ---------------------------------------------------------------------------

#: Matches the same bare numeric-literal IR operand shape
#: :func:`_translate_operand` itself recognises (rule 3). Duplicated rather
#: than shared so this module's public translation rule is not disturbed by
#: a change scoped to DISPLAY formatting alone.
_NUMERIC_OPERAND_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")


def _format_display_operand(
    operand: str,
    java_operand: str,
    context: ConditionContext | None,
    subscripted: bool = False,
) -> str:
    """
    Apply COBOL DISPLAY's implicit PICTURE formatting to *java_operand*,
    when *operand* is a plain field reference whose declared width is known.

    A COBOL ``DISPLAY`` of an elementary item is not "print the value" --
    it is "print exactly the item's storage", which for an unedited
    ``USAGE DISPLAY`` PICTURE means the value is already zero-padded
    (numeric) or space-padded (alphanumeric) to the declared width by the
    runtime *before* ``DISPLAY`` ever sees it. The Java backend has no such
    storage representation (a COBOL ``PIC 9(3)`` becomes a plain Java
    ``int``), so without this, the printed value has whatever width the
    number or string naturally prints with (``5``, not ``"005"``).

    Scope (Category A only -- see ``docs/MMIM_DISPLAY_FORMATTING_FIX.md``):
        - Unsigned ``PIC 9(n)``      → zero-padded to *n* digits.
        - Unsigned ``PIC 9(n)V9(m)`` → zero-padded to *n+m* digits, with the
          assumed decimal point never printed (COBOL DISPLAY never prints
          ``V``).
        - ``PIC X(n)``               → space-padded (right-justified) to
          *n* characters.

    Deliberately NOT formatted (left exactly as *java_operand*, matching
    behavior before #stage31):
        - A signed field (``PIC S9...``) -- ``JavaField.signed`` is ``True``.
        - A group item ``DISPLAY``, or any field whose type could not be
          resolved -- ``JavaField.digits``/``length`` are both ``None``.
        - A quoted string literal or a bare numeric literal operand -- it is
          not a field reference at all, so no declared width exists for it.
        - Anything else *context* does not know about (no *context*, or the
          operand does not resolve to a declared field).
        - (task #stage33) A bare, *unsubscripted* reference to an
          ``OCCURS`` field (:attr:`~app.backend.java.field_model.JavaField.occurs`
          is not ``None``) -- its declared ``digits``/``length`` describe
          one *element*, not the Java array itself, and formatting the
          array reference as if it were that element would not compile.
          This mirrors Stage 31's own documented gap ("OCCURS/subscripted
          item DISPLAY" in ``docs/MMIM_DISPLAY_FORMATTING_FIX.md`` §11) --
          still deliberately unformatted, now for a precise, checked
          reason instead of never being reachable at all. A *subscripted*
          reference to one element of that same field (``subscripted=True``)
          is formatted exactly like any other elementary field.

    Args:
        operand:
            The raw IR operand string (before translation), used only to
            tell a field reference apart from a literal.
        java_operand:
            *operand* already translated via :func:`_translate_operand` --
            the expression this function may wrap.
        context:
            Optional :class:`~app.backend.java.condition_context.ConditionContext`.
            ``None`` returns *java_operand* unchanged.
        subscripted:
            ``True`` when *operand* carried a structured subscript (task
            #stage32) that :func:`_translate_operand` already applied to
            *java_operand* -- i.e. *java_operand* names one array element,
            not the whole array. Defaults to ``False``, reproducing every
            pre-#stage33 caller's behavior exactly.

    Returns:
        A Java expression string: either *java_operand* unchanged, or a
        ``String.format(...)`` call wrapping it.

    Examples:
        >>> from app.backend.java.condition_context import ConditionContext
        >>> from app.backend.java.field_model import JavaField
        >>> ctx = ConditionContext(
        ...     fields={"wsCount": JavaField(java_name="wsCount",
        ...                                  java_type="int", digits=3)}
        ... )
        >>> _format_display_operand("WS-COUNT", "wsCount", ctx)
        'String.format("%03d", wsCount)'
        >>> _format_display_operand("WS-COUNT", "wsCount", None)
        'wsCount'
    """
    if context is None:
        return java_operand

    # Only a plain field reference has a declared width; a literal has none.
    if operand.startswith('"') or operand.startswith("'"):
        return java_operand
    if _NUMERIC_OPERAND_RE.match(operand):
        return java_operand

    # task #stage33: look up the *base* field, never the (possibly
    # subscripted) rendered expression -- context.fields is keyed by plain
    # Java field name, so "wsItem[1]" would never be found.
    fld = context.fields.get(to_java_field_name(operand))
    if fld is None:
        return java_operand

    # task #stage33: an OCCURS field's digits/length describe one element;
    # only apply them when *java_operand* already names one (subscripted).
    if fld.occurs is not None and not subscripted:
        return java_operand

    if fld.digits is not None and not fld.signed:
        width = fld.digits
        if fld.decimal_places:
            scale = 10**fld.decimal_places
            return (
                f'String.format("%0{width}d", ' f"Math.round({java_operand} * {scale}))"
            )
        return f'String.format("%0{width}d", {java_operand})'

    if fld.length is not None:
        return f'String.format("%-{fld.length}s", {java_operand})'

    return java_operand
