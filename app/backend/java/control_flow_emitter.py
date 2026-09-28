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

    Except (only when *context* is given): a ``ZERO``/``ZEROS``/``ZEROES`` or
    ``SPACE``/``SPACES`` figurative-constant operand goes through
    :func:`~app.backend.java.condition_context.translate_figurative_operand`
    first (task #stage31), becoming a type-compatible Java literal (``0``,
    ``0.0``, ``""``) instead of rule 3's undeclared-identifier fallback --
    see that function's docstring for exactly when it applies.

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

from app.backend.java.condition_context import (
    ConditionContext,
    translate_comparison,
    translate_condition_name,
    translate_figurative_operand,
)
from app.backend.java.generator import BackendDiagnostic, BackendSeverity

if TYPE_CHECKING:
    from app.ir.instructions import (
        IRArithmeticExpression,
        IRIf,
        IRPerformUntil,
        IRPerformVarying,
        IRSubscript,
    )

__all__ = [
    "OPERATOR_ALIASES",
    "SUPPORTED_OPERATORS",
    "emit_else",
    "emit_end_if",
    "emit_end_perform",
    "emit_if",
    "emit_perform_until",
    "emit_perform_varying",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_OPERATORS: frozenset[str] = frozenset({"==", "!=", ">", ">=", "<", "<="})
"""The set of Java comparison operators :func:`emit_if` can emit."""

_CONDITION_NAME_OPERATORS: frozenset[str] = frozenset({"IS-TRUE", "IS-FALSE"})
"""The IR sentinels for a level-88 condition-name reference (``IF NAME`` /
``IF NOT NAME``); see :mod:`app.backend.java.condition_context`."""

OPERATOR_ALIASES: dict[str, str] = {"=": "==", "<>": "!="}
"""COBOL spellings the parser passes through unchanged, mapped to the Java
operator they mean. COBOL's equality operator is ``=``; the parser and IR
builder keep it as ``=`` (they never normalise operators), so without this
alias every ``IF``/``PERFORM UNTIL`` using the most common COBOL comparison
was rejected as unsupported. ``<>`` is COBOL's own "not equal" spelling
(task #stage25) -- including the one a parser-level ``NOT =`` negation
normalises to (see :meth:`~app.parser.syntax.procedure_parser
.ProcedureDivisionParser._parse_simple_condition`) -- and is aliased the
same way, to the already-supported ``!=``. Kept separate from
:data:`SUPPORTED_OPERATORS` so that set's meaning (the Java operators) is
unchanged."""


# ---------------------------------------------------------------------------
# emit_if — IRIf → Java ``if (<condition>) {``
# ---------------------------------------------------------------------------


def emit_if(
    instruction: IRIf,
    depth: int,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
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
        - ``IF WS-A > 5 OR WS-B < 2`` → ``if (wsA > 5 || wsB < 2) {``
          (every ``extra_terms`` term is kept, in order; ``AND`` → ``&&``,
          ``OR`` → ``||``; an AND-run inside an ``OR`` chain is
          parenthesised for readability -- Java's ``&&``-over-``||``
          precedence already matches COBOL's ``AND``-over-``OR``.) If any
          one term cannot be translated the whole IF header is skipped
          with that term's ``BE007`` diagnostic -- never emitted with a
          term silently missing.
        - ``IF WS-ITEM(WS-I) > 100`` → ``if (wsItem[wsI - 1] > 100) {``
          (task #stage33 — ``instruction.left_subscript``/
          ``right_subscript``, and per-term for a compound condition;
          see :func:`_build_condition`).
        - ``IF (A + B) > C`` → ``if ((a + b) > c) {`` (task #stage38 —
          ``instruction.left_expression``/``right_expression``, reusing
          ``COMPUTE``'s expression rendering unchanged; see
          :func:`_build_condition`).

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRIf` to translate.
        depth:
            Current nesting depth of this header line (0 = flat inside main).
        diagnostics:
            Mutable list; ``BE007`` diagnostics appended on error.
        context:
            Optional :class:`~app.backend.java.condition_context.ConditionContext`
            (field types + level-88 condition-names). With it, ``=``/``!=``
            between two text operands is a COBOL text comparison and a
            level-88 condition reference is translated; without it every
            condition is translated exactly as before.

    Returns:
        A list containing exactly one ``if (<cond>) {`` string, or an empty
        list when the condition cannot be translated.
    """
    condition = _build_if_condition(instruction, diagnostics, context)
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
# emit_perform_until — IRPerformUntil → Java ``while (!(<condition>)) {``
# ---------------------------------------------------------------------------


def emit_perform_until(
    instruction: IRPerformUntil,
    depth: int,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRPerformUntil` into a Java
    ``while (!(<condition>)) {`` header line.

    The prefix ``"    " * depth`` is prepended to position the header at the
    correct nesting level within ``main()``.

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRPerformUntil` to translate.
        depth:
            Current nesting depth of this header line (0 = flat inside main).
        diagnostics:
            Mutable list; ``BE007`` diagnostics appended on error.
        context:
            Optional condition context; see :func:`emit_if`.

    Returns:
        A list containing exactly one ``while (!(<cond>)) {`` string, or an empty
        list when the condition cannot be translated.
    """
    condition = _build_condition(
        instruction.left,
        instruction.operator,
        instruction.right,
        diagnostics,
        context,
    )
    if condition is None:
        return []

    prefix = "    " * depth
    return [f"{prefix}while (!({condition})) {{"]


# ---------------------------------------------------------------------------
# emit_end_perform — emit ``}``
# ---------------------------------------------------------------------------


def emit_end_perform(
    depth: int,
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """
    Emit a Java closing brace ``}`` for a PERFORM block at the given *depth*.

    Args:
        depth:
            The nesting depth of the **perform-header** (same level as the closing
            brace — one less than the body depth).
        diagnostics:
            Mutable list; currently unused but kept for API symmetry.

    Returns:
        A list containing exactly one ``}`` string with the appropriate depth prefix.
    """
    prefix = "    " * depth
    return [f"{prefix}}}"]


# ---------------------------------------------------------------------------
# emit_perform_varying — IRPerformVarying → Java ``for (...; ...; ...) {``
# ---------------------------------------------------------------------------

#: UNTIL-condition operators (after COBOL-alias translation, task #stage25)
#: this stage knows how to invert into a *simplified* Java loop
#: continue-condition, mapped to the inverted operator. Evidenced
#: directly: the task's own worked example (``UNTIL x > 4`` ->
#: ``x <= 4``) and its explicitly-given second rule (``UNTIL x >= 4`` ->
#: ``x < 4``); independently confirmed as the *only* relational form any
#: of the real corpus's five ``PERFORM VARYING`` occurrences ever use
#: (every one is ``UNTIL <idx> > <literal>``). Any other operator (``<``,
#: ``<=``, ``=``/``==``, ``<>``/``!=``) falls back to
#: :func:`_build_loop_continue_condition`'s always-correct ``!(...)``
#: wrap -- the same mechanism plain ``PERFORM UNTIL``
#: (:func:`emit_perform_until`) already uses for every operator -- rather
#: than guessing a second algebraic inversion this task has no evidence
#: for.
_UNTIL_OPERATOR_INVERSION: dict[str, str] = {">": "<=", ">=": "<"}


def _build_loop_continue_condition(
    left: str,
    operator: str,
    right: str,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None,
    left_subscript: tuple[IRSubscript, ...] = (),
    right_subscript: tuple[IRSubscript, ...] = (),
) -> str | None:
    """
    Build a Java ``for`` loop's continue-condition from a COBOL
    ``PERFORM VARYING ... UNTIL <left> <operator> <right>`` exit
    condition (task #stage34).

    A COBOL ``UNTIL`` loop continues while its condition is *false*; a
    Java ``for`` loop's middle clause is its own continue condition -- the
    logical opposite. Reuses :func:`_build_condition` for validation and
    translation (so an empty operand, an unsupported operator, a COBOL
    text comparison, a figurative-constant operand, or a level-88
    condition-name reference are all handled identically to ``IF`` --
    including subscripted operands, task #stage32/#stage33, through the
    same shared renderer), then either:

    * Renders the simplified inverted form for the two operators
      :data:`_UNTIL_OPERATOR_INVERSION` covers (``>``/``>=``) -- these
      never reach ``_build_condition``'s text-comparison path (that path
      is equality-only), so independently re-translating the operands
      here reproduces exactly what ``_build_condition`` itself would
      have used for them.
    * Falls back to ``!(<condition>)`` for every other shape -- always
      correct, and the same wrapping plain ``PERFORM UNTIL`` already uses.

    Returns:
        The Java continue-condition expression, or ``None`` if the
        condition could not be translated at all (the caller then omits
        the whole loop, exactly like an untranslatable ``IF``).
    """
    # Import here to avoid circular imports at module level (mirrors
    # _build_condition's own deferred import of the same module).
    from app.backend.java.statement_emitter import _translate_operand

    built = _build_condition(
        left,
        operator,
        right,
        diagnostics,
        context,
        left_subscript=left_subscript,
        right_subscript=right_subscript,
    )
    if built is None:
        return None

    java_operator = OPERATOR_ALIASES.get(operator, operator)
    inverted = _UNTIL_OPERATOR_INVERSION.get(java_operator)
    if inverted is not None:
        java_left = translate_figurative_operand(
            left, right, java_operator, context
        ) or _translate_operand(left, left_subscript)
        java_right = translate_figurative_operand(
            right, left, java_operator, context
        ) or _translate_operand(right, right_subscript)
        return f"{java_left} {inverted} {java_right}"

    return f"!({built})"


def emit_perform_varying(
    instruction: IRPerformVarying,
    depth: int,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate an :class:`~app.ir.instructions.IRPerformVarying` into a
    Java ``for (<init>; <continue>; <step>) {`` header line (task
    #stage34).

    The prefix ``"    " * depth`` is prepended to position the header at
    the correct nesting level within ``main()``, exactly like
    :func:`emit_if`/:func:`emit_perform_until`.

    Rules:
        - ``PERFORM VARYING CURRENT-IDX FROM 1 BY 1 UNTIL CURRENT-IDX > 4``
          → ``for (currentIdx = 1; currentIdx <= 4; currentIdx += 1) {``
        - ``BY -1`` → the step becomes ``currentIdx += -1`` (never a
          second ``-=`` form -- ``+=`` with a negative operand is the
          existing project style, matching how a negative ``ADD``/
          arithmetic operand is already rendered elsewhere).
        - A subscripted ``UNTIL`` operand (task #stage32/#stage33) is
          rendered through the exact same shared subscript renderer
          every other emitter uses -- see
          :func:`_build_loop_continue_condition`.

    The varying variable is rendered via
    :func:`~app.backend.java.naming.to_java_field_name` (through
    :func:`~app.backend.java.statement_emitter._render_reference`, the
    same function every other plain identifier reference in this
    backend already goes through) -- it is the same Java field every
    subscripted body reference to it resolves to, never a separate
    hidden loop variable.

    Args:
        instruction:
            The :class:`~app.ir.instructions.IRPerformVarying` to
            translate.
        depth:
            Current nesting depth of this header line (0 = flat inside
            main).
        diagnostics:
            Mutable list; ``BE007`` diagnostics appended on error.
        context:
            Optional :class:`~app.backend.java.condition_context.ConditionContext`;
            see :func:`emit_if`.

    Returns:
        A list containing exactly one ``for (...) {`` string, or an empty
        list when the varying variable, ``FROM``/``BY`` operand, or
        ``UNTIL`` condition cannot be translated.
    """
    # Import here to avoid circular imports at module level (mirrors
    # _build_condition's own deferred import of the same module).
    from app.backend.java.statement_emitter import _render_reference, _translate_operand

    if not instruction.varying_variable:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRPerformVarying has empty varying variable; skipping loop.",
                code="BE007",
            )
        )
        return []

    if not instruction.from_value:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"IRPerformVarying for '{instruction.varying_variable}' has "
                    "empty FROM operand; skipping loop."
                ),
                code="BE007",
            )
        )
        return []

    if not instruction.by_value:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"IRPerformVarying for '{instruction.varying_variable}' has "
                    "empty BY operand; skipping loop."
                ),
                code="BE007",
            )
        )
        return []

    condition = _build_loop_continue_condition(
        instruction.left,
        instruction.operator,
        instruction.right,
        diagnostics,
        context,
        left_subscript=instruction.left_subscript,
        right_subscript=instruction.right_subscript,
    )
    if condition is None:
        return []

    java_var = _render_reference(instruction.varying_variable)
    java_from = _translate_operand(instruction.from_value)
    java_by = _translate_operand(instruction.by_value)

    prefix = "    " * depth
    return [
        f"{prefix}for ({java_var} = {java_from}; {condition}; "
        f"{java_var} += {java_by}) {{"
    ]


# ---------------------------------------------------------------------------
# Internal condition builder
# ---------------------------------------------------------------------------


_JAVA_CONNECTORS: dict[str, str] = {"AND": "&&", "OR": "||"}


def _build_if_condition(
    instruction: IRIf,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
) -> str | None:
    """
    Translate an ``IRIf``'s whole condition (first term plus ``extra_terms``)
    into one Java boolean expression, or ``None`` if any term cannot be
    translated (that term's ``BE007`` diagnostic is already recorded).
    """
    first = _build_condition(
        instruction.left,
        instruction.operator,
        instruction.right,
        diagnostics,
        context,
        left_subscript=instruction.left_subscript,
        right_subscript=instruction.right_subscript,
        left_expression=instruction.left_expression,
        right_expression=instruction.right_expression,
    )
    if first is None:
        return None
    if not instruction.extra_terms:
        return first

    # OR-separated runs of AND-connected terms (AND binds tighter than OR).
    runs: list[list[str]] = [[first]]
    for term in instruction.extra_terms:
        connector = (term.connector or "").upper()
        if connector not in _JAVA_CONNECTORS:
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=(
                        f"IRIf has unsupported condition connector '{term.connector}'; "
                        "supported connectors are ['AND', 'OR']. Skipping IF block."
                    ),
                    code="BE007",
                )
            )
            return None
        java_term = _build_condition(
            term.left,
            term.operator,
            term.right,
            diagnostics,
            context,
            left_subscript=term.left_subscript,
            right_subscript=term.right_subscript,
            left_expression=term.left_expression,
            right_expression=term.right_expression,
        )
        if java_term is None:
            return None
        if connector == "AND":
            runs[-1].append(java_term)
        else:
            runs.append([java_term])

    if len(runs) == 1:
        return " && ".join(runs[0])
    return " || ".join(
        run[0] if len(run) == 1 else "(" + " && ".join(run) + ")" for run in runs
    )


def _build_condition(
    left: str,
    operator: str,
    right: str,
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None = None,
    left_subscript: tuple[IRSubscript, ...] = (),
    right_subscript: tuple[IRSubscript, ...] = (),
    left_expression: "IRArithmeticExpression | None" = None,
    right_expression: "IRArithmeticExpression | None" = None,
) -> str | None:
    """
    Validate and translate a condition triple into a Java expression string.

    Validation rules (each violation appends a ``BE007`` WARNING and returns
    ``None``):

    1. ``left`` must not be empty, unless *left_expression* is given.
    2. ``operator`` must be one of :data:`SUPPORTED_OPERATORS`, or a COBOL
       spelling in :data:`OPERATOR_ALIASES` (``=`` is emitted as ``==``).
    3. ``right`` must not be empty, unless *right_expression* is given.

    If all checks pass, both operands are translated via
    :func:`~app.backend.java.statement_emitter._translate_operand` -- which
    also applies *left_subscript*/*right_subscript* (task #stage32/#stage33:
    ``IF WS-ITEM(WS-I) > 100`` → ``wsItem[wsI - 1] > 100``), through the
    same single shared subscript renderer every other emitter uses, never a
    condition-path-specific one -- and the result is assembled as
    ``"<java_left> <operator> <java_right>"`` -- except (only when *context*
    is given) that

    * ``=``/``!=`` between two operands that are both *known text* (a quoted
      literal or a ``String`` field) is a COBOL alphanumeric comparison,
      ``_cobolEquals(l, r)`` / ``!_cobolEquals(l, r)``, because Java ``==``
      on two ``String`` references compares object identity, not characters;
      numeric, mixed, unknown-typed and ordering comparisons are unchanged;
    * the level-88 sentinels ``IS-TRUE``/``IS-FALSE`` are translated when
      *context* knows the condition-name, and reported (``BE007``) with the
      reason when it cannot be translated safely;
    * a ``ZERO``/``ZEROS``/``ZEROES`` or ``SPACE``/``SPACES`` operand is
      translated to a type-compatible Java literal using the *other*
      operand's known type (task #stage31,
      :func:`~app.backend.java.condition_context.translate_figurative_operand`);
      an operand this cannot prove type-compatible keeps its old,
      undeclared-identifier translation.

    Args:
        left:
            Left-hand IR operand string.
        operator:
            Comparison operator string (e.g. ``">"``, ``"==\"``).
        right:
            Right-hand IR operand string.
        diagnostics:
            Mutable list; ``BE007`` diagnostics appended on error.
        context:
            Optional field-type / condition-name context.
        left_subscript / right_subscript:
            Zero or one structured ``IRSubscript`` (task #stage32) for
            *left*/*right*. Empty by default so every pre-#stage33 caller
            is unaffected.
        left_expression / right_expression:
            A structured arithmetic-expression tree (task #stage38,
            reusing ``COMPUTE``'s representation unchanged) for
            *left*/*right*, when that operand is a parenthesized
            expression rather than a plain operand -- e.g.
            ``IF (A + B) > C``. ``None`` by default so every
            pre-#stage38 caller is unaffected; when given, the
            corresponding *left*/*right* string is ignored (it is ``""``
            for that side, by construction -- the two are mutually
            exclusive, never both consulted) and *left*/*right* being
            empty does not itself fail validation rule 1/3 above.

    Returns:
        A Java condition expression string such as ``"wsCount > 0"`` or
        ``None`` when validation fails.
    """
    # Import here to avoid circular imports at module level.
    from app.backend.java.statement_emitter import (
        _translate_expression,
        _translate_operand,
    )

    if not left and left_expression is None:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRIf has empty left operand; skipping IF block.",
                code="BE007",
            )
        )
        return None

    if (
        left_expression is None
        and context is not None
        and operator in _CONDITION_NAME_OPERATORS
        and left.upper() in context.condition_names
    ):
        expression, reason = translate_condition_name(
            left, operator == "IS-TRUE", context
        )
        if expression is not None:
            return expression
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"Level-88 condition '{left}' cannot be translated: {reason}. "
                    "Skipping IF block."
                ),
                code="BE007",
            )
        )
        return None

    java_operator = OPERATOR_ALIASES.get(operator, operator)
    if java_operator not in SUPPORTED_OPERATORS:
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

    if not right and right_expression is None:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message="IRIf has empty right operand; skipping IF block.",
                code="BE007",
            )
        )
        return None

    # An arithmetic-expression operand (task #stage38) is always numeric --
    # never COBOL text, never a figurative constant -- so when either side
    # is one, the COBOL-text-equality and figurative-constant paths below
    # (which only ever make sense between two plain operands) are skipped
    # entirely for this condition, and each side is rendered directly:
    # _translate_expression (the exact same renderer emit_compute already
    # uses for COMPUTE, reused unchanged) for the expression side, the
    # ordinary plain-operand path for the other side.
    if left_expression is not None or right_expression is not None:
        java_left = (
            _translate_expression(left_expression)
            if left_expression is not None
            else (
                translate_figurative_operand(left, right, java_operator, context)
                or _translate_operand(left, left_subscript)
            )
        )
        java_right = (
            _translate_expression(right_expression)
            if right_expression is not None
            else (
                translate_figurative_operand(right, left, java_operator, context)
                or _translate_operand(right, right_subscript)
            )
        )
        return f"{java_left} {java_operator} {java_right}"

    text_comparison = translate_comparison(
        left,
        java_operator,
        right,
        context,
        left_subscript=left_subscript,
        right_subscript=right_subscript,
    )
    if text_comparison is not None:
        return text_comparison

    java_left = translate_figurative_operand(
        left, right, java_operator, context
    ) or _translate_operand(left, left_subscript)
    java_right = translate_figurative_operand(
        right, left, java_operator, context
    ) or _translate_operand(right, right_subscript)
    return f"{java_left} {java_operator} {java_right}"
