"""
Java Class Generator.

Purpose:
    Translate an :class:`~app.ir.program.IRProgram` into a valid Java source
    string.

    The generator produces a deterministic Java class containing:

    * Java instance field declarations (from IR data symbols, TASK-033).
    * A ``public static void main(String[] args)`` entry-point method.
    * ``// IR: <instruction>`` comment stubs for each IR instruction.

    Statement generation is intentionally deferred to later tasks.

Design:
    The generation pipeline operates on the IR *without* accessing the COBOL
    AST directly.  Field declarations are built from
    :class:`~app.backend.java.field_model.JavaField` objects that callers
    construct (usually via :func:`build_fields_from_symbols`) and pass as the
    ``fields`` argument.

    Class naming follows these rules, applied in order:

    1. Use the first module's ``name`` field if non-empty.
    2. Fall back to the ``IRProgram.name`` field if non-empty.
    3. Fall back to the default ``"GeneratedProgram"`` if both are empty.

    The name is sanitised with :func:`_to_java_class_name` before use.

Responsibilities:
    - Derive a valid Java identifier for the class name from the IR.
    - Render Java field declarations (TASK-033).
    - Emit the class declaration, ``main`` method, and closing braces.
    - Emit a ``// IR: <instruction>`` comment stub for each instruction in the
      entry basic block (statement lowering is a future task).
    - Collect and return :class:`BackendDiagnostic` records for invalid IR
      (missing name, unsupported types) without raising exceptions.
    - Return a non-empty string even when diagnostics are emitted.

Non-responsibilities:
    - Statement lowering (deferred to TASK-034+).
    - Spring Boot / Maven project generation.
    - Writing files to disk.
    - Optimisation.

Dependencies:
    - :mod:`app.ir.program`               — ``IRProgram``, ``IRModule``, ``IRFunction``.
    - :mod:`app.ir.blocks`                — ``IRBasicBlock``.
    - :mod:`app.ir.instructions`          — ``IRInstruction`` (for comment stubs).
    - :mod:`app.ir.printer`               — :func:`~app.ir.printer._format_instruction`.
    - :mod:`app.backend.java.field_model` — ``JavaField``.
    - :mod:`app.backend.java.naming`      — :func:`to_java_field_name`.
    - :mod:`app.backend.java.type_mapper` — :func:`map_cobol_type`.
    - Python standard library only (``re``, ``dataclasses``).

Examples:
    Generating a Java class with fields::

        from app.ir.program import IRProgram
        from app.backend.java.generator import generate
        from app.backend.java.field_model import JavaField

        fields = [JavaField(java_name="wsGreeting", java_type="String",
                            initial_value='"WELCOME"')]
        src = generate(IRProgram(name="HELLO"), fields=fields)
        assert "private String wsGreeting" in src

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, unique
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.backend.java.condition_context import (
    COBOL_EQUALS,
    COBOL_EQUALS_HELPER,
    ConditionContext,
    ConditionName,
    build_condition_context,
)
from app.backend.java.field_model import JavaField
from app.backend.java.naming import to_java_field_name
from app.backend.java.type_mapper import map_cobol_type
from app.backend.java.value_initializer import translate_value_literal

if TYPE_CHECKING:
    from app.ir.program import IRProgram
    from app.parser.semantic.symbols import VariableSymbol

# Imported after class definitions to avoid circular imports at module level.
# statement_emitter imports BackendDiagnostic / BackendSeverity from this module.

__all__ = [
    "BackendDiagnostic",
    "BackendSeverity",
    "GenerationResult",
    "build_fields_from_symbols",
    "generate",
    "generate_with_diagnostics",
]

# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@unique
class BackendSeverity(Enum):
    """Severity level for backend diagnostics."""

    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class BackendDiagnostic:
    """
    Immutable record produced by the Java generator when it encounters
    invalid or incomplete IR.

    Attributes:
        severity:
            :class:`BackendSeverity.WARNING` or :class:`BackendSeverity.ERROR`.
        message:
            Human-readable description of the issue.
        code:
            Short diagnostic code for programmatic handling (e.g. ``"BE001"``).
    """

    severity: BackendSeverity = field(default=BackendSeverity.ERROR)
    message: str = field(default="")
    code: str = field(default="")


@dataclass
class GenerationResult:
    """
    Aggregated output of :func:`generate`.

    Attributes:
        source:
            The generated Java source string.  Always non-empty; contains at
            least a minimal class skeleton even when diagnostics are present.
        diagnostics:
            List of :class:`BackendDiagnostic` records collected during
            generation.
    """

    source: str = field(default="")
    diagnostics: list[BackendDiagnostic] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Return ``True`` if any error-level diagnostics were produced."""
        return any(d.severity is BackendSeverity.ERROR for d in self.diagnostics)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#: COBOL level number of a condition-name entry (``88 NAME VALUE ...``).
_CONDITION_NAME_LEVEL = 88


def build_fields_from_symbols(
    symbols: list[VariableSymbol],
    diagnostics: list[BackendDiagnostic] | None = None,
) -> list[JavaField]:
    """
    Convert a list of :class:`~app.parser.semantic.symbols.VariableSymbol`
    objects into :class:`~app.backend.java.field_model.JavaField` objects.

    A level-88 condition-name is skipped: it is a named *condition on its
    parent data item*, not storage, so it gets no Java field (a
    ``private String isDep;`` would imply state that does not exist, and
    nothing ever reads or writes it).  The symbol stays in the symbol table
    and the ``VALUE``/``VALUES`` literals stay on the AST's
    ``ConditionNameNode``; a condition reference in an ``IF`` is lowered as
    the ``IS-TRUE``/``IS-FALSE`` IR sentinel, which the backend still reports
    as untranslatable (``BE007``) rather than guessing.

    For every other symbol:

    1. The COBOL name is converted to lowerCamelCase via
       :func:`~app.backend.java.naming.to_java_field_name`.
    2. The ``cobol_type`` is mapped to a Java type via
       :func:`~app.backend.java.type_mapper.map_cobol_type`.  Symbols without
       a type (``cobol_type is None``) are skipped with a ``BE003`` WARNING.
    3. A ``VALUE`` clause becomes the field's initializer via
       :func:`~app.backend.java.value_initializer.translate_value_literal`
       (numeric literals are normalized — Java reads a leading ``0`` as
       octal).  A symbol with no ``VALUE`` clause, or one whose literal has no
       provably correct Java equivalent for the field's type, keeps no
       initializer.
    4. The declared PICTURE width/scale is copied onto the field's
       ``digits``/``decimal_places``/``signed``/``length`` attributes
       straight from ``cobol_type`` (task #stage31) — never recomputed from
       the raw PIC string — so a later stage can reproduce COBOL DISPLAY
       formatting.  A :class:`~app.parser.semantic.types.GroupType` symbol
       (also mapped to Java ``String``) gets none of these: it is not an
       elementary item and has no PICTURE of its own.

    Args:
        symbols:
            Ordered list of variable symbols from the semantic context.
        diagnostics:
            Optional mutable list to collect :class:`BackendDiagnostic` records.
            If ``None`` a local list is used (diagnostics are discarded).

    Returns:
        An ordered list of :class:`~app.backend.java.field_model.JavaField`
        objects in the same order as *symbols*, skipping any that cannot be
        mapped.
    """
    # Lazy import to preserve the backend/parser layering
    # (mirrors app.backend.java.type_mapper.map_cobol_type's own lazy import
    # of the same module).
    from app.parser.semantic.types import AlphanumericType, NumericType

    if diagnostics is None:
        diagnostics = []

    result: list[JavaField] = []

    for sym in symbols:
        if sym.level == _CONDITION_NAME_LEVEL:
            continue

        cobol_type = sym.cobol_type

        if cobol_type is None:
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=(
                        f"variable '{sym.name}' has no resolved COBOL type; "
                        "skipping field generation."
                    ),
                    code="BE003",
                )
            )
            continue

        java_type, err = map_cobol_type(cobol_type)
        if java_type is None or err is not None:
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=(
                        f"variable '{sym.name}': {err or 'unknown type mapping error'}; "
                        "skipping field generation."
                    ),
                    code="BE002",
                )
            )
            continue

        java_name = to_java_field_name(sym.name)

        digits: int | None = None
        decimal_places = 0
        signed = False
        length: int | None = None
        if isinstance(cobol_type, NumericType):
            digits = cobol_type.digits
            decimal_places = cobol_type.decimal_places
            signed = cobol_type.signed
        elif isinstance(cobol_type, AlphanumericType):
            length = cobol_type.length

        result.append(
            JavaField(
                java_name=java_name,
                java_type=java_type,
                initial_value=translate_value_literal(sym.value, java_type),
                cobol_name=sym.name,
                digits=digits,
                decimal_places=decimal_places,
                signed=signed,
                length=length,
            )
        )

    return result


def generate(
    program: IRProgram,
    fields: list[JavaField] | None = None,
) -> str:
    """
    Generate a Java class string from *program*.

    This is the primary entry point for the Java backend.  It returns the
    generated Java source code directly.  Use :func:`generate_with_diagnostics`
    if you also need access to backend diagnostics.

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` to lower to Java.
        fields:
            Optional list of :class:`~app.backend.java.field_model.JavaField`
            objects to emit as instance field declarations before ``main``.
            If ``None`` or empty, no fields are emitted.

    Returns:
        A non-empty ``str`` containing a compilable Java class.

    Examples:
        >>> from app.ir.program import IRProgram
        >>> from app.backend.java.generator import generate
        >>> src = generate(IRProgram(name="PAYROLL"))
        >>> "public class Payroll" in src
        True
        >>> "public static void main" in src
        True
    """
    result = generate_with_diagnostics(program, fields=fields)
    for diag in result.diagnostics:
        logger.warning("JavaGenerator [{}] {}", diag.code, diag.message)
    return result.source


def generate_with_diagnostics(
    program: IRProgram,
    fields: list[JavaField] | None = None,
    paragraph_order: Sequence[str] | None = None,
    condition_names: Mapping[str, ConditionName] | None = None,
) -> GenerationResult:
    """
    Generate Java source from *program* and return both the source and any
    diagnostics emitted during generation.

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` to lower to Java.
        fields:
            Optional list of :class:`~app.backend.java.field_model.JavaField`
            objects to emit as instance field declarations.
        paragraph_order:
            Optional names of *every* PROCEDURE DIVISION paragraph in source
            order (task #stage19). The IR carries no record of a paragraph
            that has no representable statements, so without this a
            ``GO TO`` to such a paragraph is indistinguishable from a
            ``GO TO`` to a paragraph that does not exist. Only names are
            passed -- the generator still never reads the AST. Consulted
            solely when the program contains a ``GO TO`` (see
            :func:`_collect_statements`).
        condition_names:
            Optional level-88 condition-names of the program
            (``{NAME: ConditionName(parent, values)}``, see
            :func:`~app.backend.java.condition_context.build_condition_names`).
            With them ``IF <condition-name>`` is translated to a comparison of
            the parent item with each declared value; without them it is
            reported untranslatable (``BE007``) exactly as before.  The IR is
            unchanged -- this is the AST metadata the IR never carried.

    Every run also knows the Java type of each of *fields*, which is what lets
    a COBOL text comparison (``=``/``!=`` between two text operands) be emitted
    as an alphanumeric comparison instead of Java ``==`` on two ``String``
    references (see :mod:`app.backend.java.condition_context`).

    Returns:
        A :class:`GenerationResult` carrying the source string and any
        :class:`BackendDiagnostic` records.
    """
    diagnostics: list[BackendDiagnostic] = []
    effective_fields: list[JavaField] = fields or []

    # ------------------------------------------------------------------
    # 1. Determine class name
    # ------------------------------------------------------------------
    class_name = _resolve_class_name(program, diagnostics)
    logger.debug("JavaGenerator: class name resolved to '{}'.", class_name)

    # ------------------------------------------------------------------
    # 2. Translate entry-block instructions into Java statements
    # ------------------------------------------------------------------
    context = build_condition_context(effective_fields, condition_names)
    statements = _collect_statements(program, diagnostics, paragraph_order, context)

    # ------------------------------------------------------------------
    # 2b. Discover CALL/PERFORM targets that have no generated method body.
    #     Each becomes an empty ``private void`` stub so the class compiles,
    #     and each raises a BE009 WARNING so the missing body is not silently
    #     swallowed.  (The bodies of internal paragraphs are dropped upstream
    #     of the backend; external sub-programs are separately compiled.)
    # ------------------------------------------------------------------
    stub_targets = _collect_call_targets(program)
    for java_name, original in stub_targets:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"CALL/PERFORM target '{original}' has no generated method "
                    f"body; emitting an empty stub 'private void {java_name}()'. "
                    "The target is either an external sub-program or a paragraph "
                    "whose body is not present in the IR; implement it in a "
                    "follow-up task."
                ),
                code="BE009",
            )
        )

    # ------------------------------------------------------------------
    # 3. Render Java source
    # ------------------------------------------------------------------
    # The alphanumeric-equality helper is emitted only by a class that uses it.
    helpers = (
        list(COBOL_EQUALS_HELPER)
        if any(f"{COBOL_EQUALS}(" in statement for statement in statements)
        else []
    )
    source = _render_class(
        class_name, effective_fields, statements, stub_targets, helpers
    )
    logger.debug(
        "JavaGenerator: generated {} line(s) for class '{}'.",
        source.count("\n"),
        class_name,
    )

    return GenerationResult(source=source, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_class_name(
    program: IRProgram,
    diagnostics: list[BackendDiagnostic],
) -> str:
    """
    Derive a valid Java class identifier from *program*.

    Resolution order:

    1. First module's ``name`` if non-empty.
    2. ``program.name`` if non-empty.
    3. ``"GeneratedProgram"`` (with a WARNING diagnostic).

    The chosen name is sanitised by :func:`_to_java_class_name`.
    """
    raw_name: str = ""

    if program.modules:
        first_module_name = program.modules[0].name
        if first_module_name:
            raw_name = first_module_name

    if not raw_name and program.name:
        raw_name = program.name

    if not raw_name:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    "IRProgram has no name and no named module; "
                    "falling back to 'GeneratedProgram'."
                ),
                code="BE001",
            )
        )
        raw_name = "GeneratedProgram"

    return _to_java_class_name(raw_name)


def _to_java_class_name(raw: str) -> str:
    """
    Convert *raw* (a COBOL program name or IR name) to a PascalCase Java
    identifier.

    Rules applied in order:

    1. Split on ``-`` and ``_`` (common COBOL conventions).
    2. Capitalise the first letter of each segment.
    3. Strip characters that are not ASCII alphanumeric or ``$``/``_``.
    4. Ensure the result starts with a letter; prepend ``"P"`` if not.
    5. Default to ``"GeneratedProgram"`` if the result is empty.

    Examples:
        >>> _to_java_class_name("HELLO-WORLD")
        'HelloWorld'
        >>> _to_java_class_name("payroll")
        'Payroll'
        >>> _to_java_class_name("")
        'GeneratedProgram'
    """
    if not raw:
        return "GeneratedProgram"

    # Split on hyphens and underscores, then PascalCase each segment.
    # All-uppercase and all-lowercase segments are fully normalised via
    # capitalize() so "HELLO" → "Hello" and "world" → "World".
    # Already-mixed-case segments (e.g. "GeneratedProgram") preserve their
    # inner case via first-letter-only capitalisation.
    segments = re.split(r"[-_]+", raw.strip())

    def _pascal_segment(seg: str) -> str:
        if not seg:
            return ""
        if seg.isupper() or seg.islower():
            return seg.capitalize()
        # Mixed-case: only uppercase the first letter, keep the rest
        return seg[0].upper() + seg[1:]

    pascal = "".join(_pascal_segment(seg) for seg in segments)

    # Remove characters not valid in Java identifiers
    pascal = re.sub(r"[^A-Za-z0-9$_]", "", pascal)

    # Ensure starts with a letter
    if pascal and not pascal[0].isalpha():
        pascal = "P" + pascal

    return pascal or "GeneratedProgram"


def _matching_close(instructions: list[Any], start: int) -> int | None:
    """Index of the ``IREndIf``/``IREndPerform`` that closes the structured
    construct opened at ``instructions[start]``, or ``None`` if the IR is
    malformed (no matching close). Nested constructs are matched by type."""
    from app.ir.instructions import IRIf, IRPerformUntil

    closers = {IRIf: "IREndIf", IRPerformUntil: "IREndPerform"}
    open_stack: list[str] = []
    for j in range(start, len(instructions)):
        instr = instructions[j]
        for opener, closer in closers.items():
            if isinstance(instr, opener):
                open_stack.append(closer)
                break
        else:
            name = type(instr).__name__
            if name in ("IREndIf", "IREndPerform"):
                if not open_stack or open_stack[-1] != name:
                    return None
                open_stack.pop()
                if not open_stack:
                    return j
    return None


def _collect_statements(
    program: IRProgram,
    diagnostics: list[BackendDiagnostic],
    paragraph_order: Sequence[str] | None = None,
    context: ConditionContext | None = None,
) -> list[str]:
    """
    Translate all instructions in the first entry basic block of the first
    function of the first module into Java statement strings.

    For regular (non-control-flow) instructions, delegates to
    :func:`~app.backend.java.statement_emitter.emit_statement` and prefixes
    each returned string with ``"    " * depth`` to reflect nesting level.

    For structured control-flow instructions (:class:`~app.ir.instructions.IRIf`,
    :class:`~app.ir.instructions.IRElse`, :class:`~app.ir.instructions.IREndIf`,
    :class:`~app.ir.instructions.IRPerformUntil`, :class:`~app.ir.instructions.IREndPerform`),
    manages a *depth* counter and calls
    :func:`~app.backend.java.control_flow_emitter.emit_if`,
    :func:`~app.backend.java.control_flow_emitter.emit_else`,
    :func:`~app.backend.java.control_flow_emitter.emit_end_if`,
    :func:`~app.backend.java.control_flow_emitter.emit_perform_until`, and
    :func:`~app.backend.java.control_flow_emitter.emit_end_perform` directly so
    that the correct indentation prefix is embedded in the returned strings.

    Depth rules:

    * :class:`~app.ir.instructions.IRIf` or :class:`~app.ir.instructions.IRPerformUntil` — emit header at current depth,
      then increment depth (body is one level deeper).
    * :class:`~app.ir.instructions.IRElse`  — decrement depth, emit the
      ``} else {`` transition at that depth, then increment depth again
      (else body is one level deeper than the header).
    * :class:`~app.ir.instructions.IREndIf` or :class:`~app.ir.instructions.IREndPerform` — decrement depth, emit the
      closing ``}`` at that depth.  If depth is already 0 when encountered, a ``BE007``
      WARNING is appended and the instruction is skipped.
    * :class:`~app.ir.instructions.IRElse` encountered at depth 0 also
      produces a ``BE007`` WARNING and is skipped.

    Untranslatable headers fail safe: when :func:`emit_if` /
    :func:`emit_perform_until` cannot translate the condition (``BE007``),
    the *whole* construct -- header, body, ``ELSE`` branch, nested constructs
    and closing instruction -- is omitted and replaced by one ``// TODO``
    comment. Emitting the body (and the closing ``}``) without its header
    would produce unbalanced Java or, if it happened to balance, run the
    guarded statements unconditionally. If the IR is malformed and the
    construct has no matching closing instruction, only the header is
    omitted (nothing is left open, nothing is swallowed).

    Reachability (post-#111 review fix, added alongside
    :class:`~app.ir.instructions.IRReturn` support): the entry block
    concatenates every paragraph's instructions flat, one after another
    (see :mod:`app.ir.builder`'s architectural note) — a paragraph that
    ends in ``STOP RUN``/``GOBACK`` is immediately followed, in the same
    straight-line instruction list, by the *next* paragraph's
    instructions. Once an :class:`~app.ir.instructions.IRReturn` lowers
    to a Java ``return;`` (see
    :func:`~app.backend.java.statement_emitter.emit_return`), anything
    emitted right after it *at the same nesting depth* would be
    unreachable code — a hard ``javac`` compile error, not merely dead
    code. A small ``dead`` stack (parallel to ``depth``) tracks this: once
    a depth's straight-line position goes dead, every further instruction
    encountered at that exact depth is skipped (no Java emitted) with a
    ``BE011`` WARNING, until depth decreases below it. Entering a nested
    IF/PERFORM-UNTIL body always starts a fresh, independently-reachable
    sub-region (an ``IRElse`` branch is reachable regardless of whether
    the preceding ``then`` branch returned, matching ``javac``'s own
    rule) unless the enclosing depth was *already* dead, in which case
    the entire nested construct is unreachable too and is skipped
    wholesale, including its header/footer, so braces stay balanced.
    This does not attempt full "both branches return" flow analysis
    (not needed by any construct the current pipeline produces); it only
    prevents the concrete, common case of trailing paragraph content
    after a top-level terminator.

    ``GO TO`` (task #stage19, :class:`~app.ir.instructions.IRJump`): Java has
    no ``goto``, and the flat model above has no notion of a paragraph, so a
    jump cannot be expressed in it. When -- and only when -- the entry block
    contains at least one ``IRJump`` whose target is a known paragraph
    (:func:`_plan_dispatch`), the whole body is lowered as a paragraph
    dispatcher instead::

        int _paragraph = 0;
        _dispatch:
        while (true) {
            switch (_paragraph) {
                case 0: // FIRST-PARA
                    ...
                case 1: // SECOND-PARA
                    ...
            }
            break _dispatch;
        }

    Every paragraph is a ``case``; because Java ``switch`` cases fall through,
    COBOL's sequential paragraph fall-through needs no extra code. A jump is
    ``_paragraph = k; continue _dispatch;`` -- forward or backward, from any
    IF nesting depth, and out of an inline ``PERFORM UNTIL`` loop (a *labeled*
    ``continue``). It is emitted as ``if (true) { ... }`` on purpose: javac
    treats an ``if`` as able to complete normally whatever its condition, so
    the statements that may follow an unconditional jump (dead code in COBOL
    too) or an IF/ELSE whose branches both jump never become an
    "unreachable statement" compile error. ``_paragraph``/``_dispatch``
    contain an underscore, which :func:`to_java_field_name` can never
    produce, so they cannot shadow or collide with a COBOL-derived name. A
    ``STOP RUN``/``GOBACK`` still makes the remainder of *its own* case
    unreachable, but the next paragraph's ``case`` label makes code reachable
    again (so the dead-region tracking is reset there). A jump whose target
    is not a paragraph of the program is left as a ``// TODO`` with a
    ``BE012`` WARNING, never guessed. Programs with no translatable jump take
    the flat path unchanged, byte for byte.

    Diagnostics produced during translation are appended to *diagnostics*.

    Returns:
        An ordered list of Java statement strings.  Control-flow headers and
        footers carry embedded depth prefixes; body statements also carry
        embedded depth prefixes.  Base 8-space ``main()`` indentation is
        applied later by :func:`_render_class`.
    """
    # Local imports to avoid circular dependencies.
    from app.backend.java.control_flow_emitter import (
        emit_else as _emit_else,
        emit_end_if as _emit_end_if,
        emit_end_perform as _emit_end_perform,
        emit_if as _emit_if,
        emit_perform_until as _emit_perform_until,
    )
    from app.backend.java.statement_emitter import emit_statement
    from app.ir.instructions import (
        IRElse,
        IREndIf,
        IREndPerform,
        IRIf,
        IRJump,
        IRPerformUntil,
        IRReturn,
    )

    statements: list[str] = []
    if not program.modules:
        return statements
    module = program.modules[0]
    if not module.functions:
        return statements
    function = module.functions[0]
    if not function.blocks:
        return statements
    block = function.blocks[0]

    depth: int = 0  # current nesting level (0 = flat inside main)
    # dead[d] -- True once an unconditional `return;` has been emitted at
    # the straight-line position currently at depth d; everything further
    # at that exact depth is unreachable until depth drops below d.
    dead: list[bool] = [False]

    def _skip_unreachable(type_name: str) -> None:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"'{type_name}' is unreachable after an unconditional "
                    "STOP RUN/GOBACK earlier in the same generated method "
                    "(paragraphs are concatenated flat); skipping to avoid "
                    "generating invalid Java."
                ),
                code="BE011",
            )
        )

    instructions = list(block.instructions)
    skip_through = -1  # last index of an omitted (untranslatable) construct

    # GO TO dispatcher state (task #stage19); inert when `plan` is None.
    plan = _plan_dispatch(instructions, paragraph_order)
    labels_at: dict[int, list[int]] = {}  # statement position -> case labels
    labelled_upto = -1  # highest case label emitted so far
    current_paragraph = ""

    def _omit_construct(index: int, what: str, omitted: str) -> None:
        """Replace the construct opened at *index* by one comment and skip
        through its matching closing instruction (or just the header if the
        IR has none)."""
        nonlocal skip_through
        statements.append(
            "    " * depth + f"// TODO: {what} condition cannot be translated "
            f"(BE007); {omitted} omitted."
        )
        close = _matching_close(instructions, index)
        skip_through = close if close is not None else index

    for index, instr in enumerate(instructions):
        if index <= skip_through:
            continue
        if plan is not None and depth == 0:
            paragraph = (instr.paragraph or "").upper()
            if paragraph and paragraph != current_paragraph:
                current_paragraph = paragraph
                target_case = plan[1][paragraph]
                for case in range(labelled_upto + 1, target_case + 1):
                    labels_at.setdefault(len(statements), []).append(case)
                labelled_upto = max(labelled_upto, target_case)
                dead[0] = False  # a case label makes code reachable again
        try:
            if isinstance(instr, IRIf):
                if dead[depth]:
                    _skip_unreachable(type(instr).__name__)
                    depth += 1
                    dead.append(True)
                    continue
                stmts = _emit_if(instr, depth, diagnostics, context)
                if not stmts:
                    _omit_construct(index, "IF", "guarded block")
                    continue
                statements.extend(stmts)
                depth += 1
                dead.append(False)

            elif isinstance(instr, IRElse):
                if depth <= 0:
                    diagnostics.append(
                        BackendDiagnostic(
                            severity=BackendSeverity.WARNING,
                            message=(
                                "IRElse encountered without a matching IRIf "
                                "(depth already 0); skipping."
                            ),
                            code="BE007",
                        )
                    )
                else:
                    dead.pop()  # the 'then' branch's reachability does not carry over
                    depth -= 1
                    if dead[depth]:
                        _skip_unreachable(type(instr).__name__)
                        depth += 1
                        dead.append(True)
                        continue
                    stmts = _emit_else(depth, diagnostics)
                    statements.extend(stmts)
                    depth += 1
                    dead.append(False)

            elif isinstance(instr, IREndIf):
                if depth <= 0:
                    diagnostics.append(
                        BackendDiagnostic(
                            severity=BackendSeverity.WARNING,
                            message=(
                                "IREndIf encountered without a matching IRIf "
                                "(depth already 0); skipping."
                            ),
                            code="BE007",
                        )
                    )
                else:
                    # The branch's own dead-state is discarded here (by
                    # design, not tracked): even when the branch just
                    # closed ended in a return, the if/else statement was
                    # entered from a reachable point, so its closing brace
                    # -- and whatever follows the whole if/else -- is still
                    # reachable Java. Only the *enclosing* depth's own
                    # dead-state (checked below) matters for whether this
                    # closing brace itself was ever opened.
                    dead.pop()
                    depth -= 1
                    if dead[depth]:
                        continue  # header was skipped too; keep braces balanced
                    stmts = _emit_end_if(depth, diagnostics)
                    statements.extend(stmts)

            elif isinstance(instr, IRPerformUntil):
                if dead[depth]:
                    _skip_unreachable(type(instr).__name__)
                    depth += 1
                    dead.append(True)
                    continue
                stmts = _emit_perform_until(instr, depth, diagnostics, context)
                if not stmts:
                    _omit_construct(index, "PERFORM UNTIL", "loop body")
                    continue
                statements.extend(stmts)
                depth += 1
                dead.append(False)

            elif isinstance(instr, IREndPerform):
                if depth <= 0:
                    diagnostics.append(
                        BackendDiagnostic(
                            severity=BackendSeverity.WARNING,
                            message=(
                                "IREndPerform encountered without a matching IRPerformUntil "
                                "(depth already 0); skipping."
                            ),
                            code="BE007",
                        )
                    )
                else:
                    dead.pop()
                    depth -= 1
                    if dead[depth]:
                        continue
                    stmts = _emit_end_perform(depth, diagnostics)
                    statements.extend(stmts)

            else:
                if dead[depth]:
                    _skip_unreachable(type(instr).__name__)
                    continue

                if plan is not None and isinstance(instr, IRJump):
                    statements.extend(
                        _emit_dispatch_jump(instr, depth, plan, diagnostics)
                    )
                    continue

                # Regular (non-control-flow) statement — apply depth prefix.
                # `context` also carries each field's declared PICTURE
                # width/scale (task #stage31), letting emit_statement's
                # IRDisplay branch reproduce COBOL DISPLAY formatting.
                stmts = emit_statement(instr, diagnostics, context=context)
                indent = "    " * depth
                statements.extend(indent + s for s in stmts)

                if isinstance(instr, IRReturn):
                    dead[depth] = True

        except Exception as exc:  # noqa: BLE001
            type_name = type(instr).__name__
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=f"unhandled error lowering '{type_name}': {exc}",
                    code="BE005",
                )
            )
            statements.append(f"// ERROR: {type_name}")

    if plan is None:
        return statements
    # Paragraphs after the last one with code (empty/unsupported) still need
    # their case label so a GO TO to them resolves.
    for case in range(labelled_upto + 1, len(plan[0])):
        labels_at.setdefault(len(statements), []).append(case)
    return _wrap_dispatch(statements, labels_at, plan[0])


def _plan_dispatch(
    instructions: list[Any],
    paragraph_order: Sequence[str] | None,
) -> tuple[list[str], dict[str, int]] | None:
    """
    Decide whether the entry block must be lowered as a paragraph dispatcher.

    Returns ``None`` (=> the unchanged flat lowering) unless *instructions*
    contain an :class:`~app.ir.instructions.IRJump` whose target is a known
    paragraph. Otherwise returns ``(order, index_of)``: every paragraph name
    in source order and the upper-cased-name -> ``case`` number map.

    *paragraph_order* (every paragraph, empty ones included) is used only if
    it covers every paragraph the instructions mention; otherwise the order
    in which paragraphs first appear in the IR is used, in which case an
    empty paragraph is unknown and a jump to it stays a ``// TODO``.
    """
    from app.ir.instructions import IRJump

    if not any(isinstance(i, IRJump) for i in instructions):
        return None

    from_ir: list[str] = []
    seen: set[str] = set()
    for instr in instructions:
        name = instr.paragraph or ""
        if name and name.upper() not in seen:
            seen.add(name.upper())
            from_ir.append(name)

    order = from_ir
    if paragraph_order is not None:
        given: list[str] = []
        given_upper: set[str] = set()
        for name in paragraph_order:
            if name and name.upper() not in given_upper:
                given_upper.add(name.upper())
                given.append(name)
        if seen <= given_upper:
            order = given

    index_of = {name.upper(): case for case, name in enumerate(order)}
    if not any(
        isinstance(i, IRJump) and i.target.upper() in index_of for i in instructions
    ):
        return None
    return order, index_of


def _emit_dispatch_jump(
    instr: Any,
    depth: int,
    plan: tuple[list[str], dict[str, int]],
    diagnostics: list[BackendDiagnostic],
) -> list[str]:
    """Lower one ``IRJump`` inside a dispatcher (see :func:`_collect_statements`)."""
    order, index_of = plan
    indent = "    " * depth
    case = index_of.get(instr.target.upper())
    if case is None:
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"GO TO target '{instr.target}' is not a paragraph of this "
                    "program; the jump was not translated."
                ),
                code="BE012",
            )
        )
        return [
            indent + f"// TODO: GO TO '{instr.target}' cannot be translated "
            "(BE012); the target is not a paragraph of this program."
        ]
    return [
        indent + f"if (true) {{ _paragraph = {case}; continue _dispatch; }} "
        f"// GO TO {order[case]}"
    ]


def _wrap_dispatch(
    statements: list[str],
    labels_at: dict[int, list[int]],
    order: list[str],
) -> list[str]:
    """Wrap the collected body in the ``_dispatch``/``switch`` skeleton,
    inserting each ``case`` label at its recorded statement position."""
    out = [
        "int _paragraph = 0;",
        "_dispatch:",
        "while (true) {",
        "    switch (_paragraph) {",
    ]
    for position in range(len(statements) + 1):
        for case in labels_at.get(position, []):
            out.append(f"        case {case}: // {order[case]}")
        if position < len(statements):
            out.append("            " + statements[position])
    out += ["    }", "    break _dispatch;", "}"]
    return out


def _collect_call_targets(program: IRProgram) -> list[tuple[str, str]]:
    """
    Collect CALL/PERFORM targets in the entry block that need a stub method.

    Scans the same entry basic block that :func:`_collect_statements` lowers
    and returns, for every :class:`~app.ir.instructions.IRCall`, the pair
    ``(java_method_name, original_target)``.  The Java name is derived with
    exactly the same quote-stripping and :func:`to_java_field_name` conversion
    used by :func:`~app.backend.java.statement_emitter.emit_call`, so the stub
    method name is guaranteed to match the invocation the emitter produced.

    A CALL target in COBOL is either an external sub-program (``CALL "NAME"``)
    or, via PERFORM lowering, an internal paragraph.  In both cases the current
    pipeline provides no method body: external sub-programs are separately
    compiled units, and paragraph bodies are not carried into the entry block.
    Emitting an empty ``private void`` stub keeps the generated class
    self-compiling without inventing behaviour or discarding the invocation.

    Results preserve first-encountered order and are de-duplicated, so a target
    invoked twice yields a single stub.

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` being lowered.

    Returns:
        An ordered, de-duplicated list of ``(java_name, original_target)``
        tuples — one per distinct CALL/PERFORM target.
    """
    from app.ir.instructions import IRCall

    targets: list[tuple[str, str]] = []
    seen: set[str] = set()

    if not program.modules:
        return targets
    module = program.modules[0]
    if not module.functions:
        return targets
    function = module.functions[0]
    if not function.blocks:
        return targets
    block = function.blocks[0]

    for instr in block.instructions:
        if not isinstance(instr, IRCall):
            continue
        target = instr.target
        if not target:
            continue
        # Mirror emit_call's quote-stripping so the stub name matches the call.
        if target.startswith('"') and target.endswith('"') and len(target) >= 2:
            target = target[1:-1]
        elif target.startswith("'") and target.endswith("'") and len(target) >= 2:
            target = target[1:-1]

        java_name = to_java_field_name(target)
        if java_name in seen:
            continue
        seen.add(java_name)
        targets.append((java_name, target))

    return targets


def _render_class(
    class_name: str,
    fields: list[JavaField],
    statements: list[str],
    stub_targets: list[tuple[str, str]] | None = None,
    helpers: list[str] | None = None,
) -> str:
    """
    Render the complete Java class source string.

    Args:
        class_name:
            A valid Java identifier used as the class name.
        fields:
            List of :class:`~app.backend.java.field_model.JavaField` objects
            to emit as instance fields before the ``main`` method.
        statements:
            Ordered list of Java statement strings to emit inside the instance
            ``run`` method.  Each string is indented with 8 spaces.
        stub_targets:
            Optional list of ``(java_name, original_target)`` pairs for
            CALL/PERFORM targets that need an empty ``private void`` stub method
            so the generated class compiles.
        helpers:
            Optional pre-indented lines of helper methods (such as the COBOL
            alphanumeric-equality helper) rendered after the stubs.

    Returns:
        A non-empty Java source string.
    """
    stubs = stub_targets or []
    lines: list[str] = []

    # Class header
    lines.append(f"public class {class_name} {{")
    lines.append("")

    # Instance field declarations
    if fields:
        for java_field in fields:
            lines.append(java_field.render())
        lines.append("")

    # main entry point: instantiate the class and invoke the instance run()
    # method.  Keeping the executable body in an *instance* method lets it
    # reference the instance fields above without the "non-static variable
    # cannot be referenced from a static context" error that a static main
    # touching instance state would raise.
    lines.append("    public static void main(String[] args) {")
    lines.append(f"        new {class_name}().run();")
    lines.append("    }")
    lines.append("")

    # Instance run() method carrying the lowered statements.  Rendered after
    # main() so that statement text appears after the "public static void main"
    # marker (a property the backend unit tests rely on).
    lines.append("    public void run() {")
    lines.append("")
    for stmt in statements:
        lines.append(f"        {stmt}")
    if statements:
        lines.append("")
    lines.append("    }")
    lines.append("")

    # Empty stub methods for CALL/PERFORM targets that have no generated body,
    # so the class compiles.  Each carries a TODO naming the original target
    # and the BE009 diagnostic emitted alongside it.
    for java_name, original in stubs:
        lines.append(f"    private void {java_name}() {{")
        lines.append(
            f"        // TODO: implement CALL/PERFORM target '{original}' (BE009)."
        )
        lines.append("    }")
        lines.append("")

    # Helper methods used by the lowered statements (only when needed).
    if helpers:
        lines.extend(helpers)
        lines.append("")

    # Class footer
    lines.append("}")
    lines.append("")

    return "\n".join(lines)
