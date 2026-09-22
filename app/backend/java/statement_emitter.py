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

from app.backend.java.condition_context import ConditionContext
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
    IRCall,
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
    IRReturn,
    IRSubtract,
)

__all__ = [
    "emit_add",
    "emit_call",
    "emit_display",
    "emit_divide",
    "emit_else",
    "emit_end_if",
    "emit_end_perform",
    "emit_if",
    "emit_move",
    "emit_multiply",
    "emit_perform_until",
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
    * :class:`~app.ir.instructions.IRAdd`      → ``+=`` compound assignment.
    * :class:`~app.ir.instructions.IRSubtract` → ``-=`` compound assignment.
    * :class:`~app.ir.instructions.IRMultiply` → ``*=`` compound assignment.
    * :class:`~app.ir.instructions.IRDivide`   → ``/=`` compound assignment.
    * :class:`~app.ir.instructions.IRCall`     → ``target(args);`` (or ``result = target(args);``).
    * :class:`~app.ir.instructions.IRReturn`   → ``return;``.
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
        context:
            Optional :class:`~app.backend.java.condition_context.ConditionContext`.
            Passed through to :func:`emit_display` (task #stage31), where it
            supplies the declared PICTURE width/scale of a DISPLAY'd field
            for zero-/space-padding.  Not otherwise consulted by this
            dispatcher: an ``IRIf``/``IRPerformUntil`` reached here (a direct
            call, not the depth-aware path in
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
    )

    if isinstance(instruction, IRMove):
        return emit_move(instruction, diagnostics)

    if isinstance(instruction, IRDisplay):
        return emit_display(instruction, diagnostics, context)

    if isinstance(instruction, IRAdd):
        return emit_add(instruction, diagnostics)

    if isinstance(instruction, IRSubtract):
        return emit_subtract(instruction, diagnostics)

    if isinstance(instruction, IRMultiply):
        return emit_multiply(instruction, diagnostics)

    if isinstance(instruction, IRDivide):
        return emit_divide(instruction, diagnostics)

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
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRDisplay` into a Java
    ``System.out.println()`` call.

    Rules:
        - ``DISPLAY "HELLO"``    → ``System.out.println("HELLO");``
        - ``DISPLAY WS-NAME``    → ``System.out.println(wsName);``
        - ``DISPLAY 42``         → ``System.out.println(42);``

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

    java_operand = _translate_operand(operand)
    java_operand = _format_display_operand(operand, java_operand, context)
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


def _translate_operand(operand: str) -> str:
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
       converted to lowerCamelCase via
       :func:`~app.backend.java.naming.to_java_field_name`.

    Args:
        operand:
            An IR operand string such as ``'"HELLO"'``, ``"'Y'"``, ``'42'``,
            or ``'WS-GREETING'``.

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

    # 4. COBOL identifier → lowerCamelCase
    return to_java_field_name(operand)


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

    fld = context.fields.get(java_operand)
    if fld is None:
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
