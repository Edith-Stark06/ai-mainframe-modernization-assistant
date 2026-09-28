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


_CONDITION_NAME_LEVEL_FOR_STACK = 88


def _resolve_array_occurs(symbols: list[VariableSymbol]) -> dict[str, int]:
    """
    Compute the ``OCCURS`` count that governs each symbol as a Java array
    (task #stage33), keyed by uppercased COBOL name.

    A symbol is governed by its *own* ``OCCURS`` clause when it has one
    (the task's worked example: ``01 WS-ITEM PIC 9(3) OCCURS 5``). Failing
    that, it is governed by the nearest **enclosing group's** ``OCCURS``
    (the shape every real corpus source actually uses:
    ``05 LINE-ITEM OCCURS 5 TIMES.`` with plain elementary children —
    ``SKU-ID``, ``QUANTITY-ORDERED``, etc. — that carry no ``OCCURS`` of
    their own). Without this second case, a subscripted reference to one of
    those children (``SKU-ID(1)``) would index into a field the first case
    alone still declares as a scalar -- an uncompilable Java array-index
    into a non-array type.

    *symbols* must be in COBOL declaration order (``SymbolTable.all_symbols``
    guarantees this) so a plain level-number stack -- the same nesting
    COBOL's own grammar defines, not a heuristic -- identifies each item's
    enclosing groups. A level-88 condition-name governs nothing and does
    not participate in the stack (it is not a data item in its own right).

    Returns:
        ``{COBOL_NAME: occurs_count}`` for every symbol that is itself, or
        is nested inside, an ``OCCURS n`` item. A group symbol appears here
        too (its own ``OCCURS``, if any) even though
        :func:`build_fields_from_symbols` deliberately does not array-ify
        it -- see that function's docstring.
    """
    result: dict[str, int] = {}
    # Each entry is (level, occurs-or-None) for one currently-open ancestor.
    stack: list[tuple[int, int | None]] = []

    for sym in symbols:
        if sym.level == _CONDITION_NAME_LEVEL_FOR_STACK:
            continue

        while stack and stack[-1][0] >= sym.level:
            stack.pop()

        governing = sym.occurs
        if governing is None:
            for _, ancestor_occurs in reversed(stack):
                if ancestor_occurs is not None:
                    governing = ancestor_occurs
                    break

        if governing is not None:
            result[sym.name.upper()] = governing

        stack.append((sym.level, sym.occurs))

    return result


def _quoted_string_content(literal: str | None) -> str | None:
    """
    Return the text between the delimiters of a quoted COBOL string
    literal, or ``None`` if *literal* is ``None`` or not one (task
    #stage39).

    A small, deliberately duplicated rule rather than a reach into
    :mod:`app.backend.java.value_initializer`'s own private, identical
    check -- the same "duplicate a well-defined, stable, two-line rule
    rather than couple to another module's underscore-prefixed helper"
    choice :func:`~app.analysis.dependencies.analyzer.is_literal_operand`
    already documents making for the same reason.
    """
    if (
        literal is not None
        and len(literal) >= 2
        and literal[0] == literal[-1]
        and literal[0] in "'\""
    ):
        return literal[1:-1]
    return None


def _resolve_redefines_values(
    symbols: list[VariableSymbol],
    diagnostics: list[BackendDiagnostic],
) -> dict[str, str]:
    """
    Derive an initial ``VALUE`` literal for every elementary child of a
    ``REDEFINES`` group, by slicing the redefined base item's own literal
    ``VALUE`` at each child's byte offset within the group (task #stage39)
    -- COBOL's own REDEFINES semantics: the redefining view shares the
    base item's storage bytes, reinterpreted under a different layout.

    Scope -- matches the one real corpus shape (``t_policy_redefines.cbl``:
    ``05 AUTO-PAYLOAD REDEFINES POLICY-RAW-PAYLOAD.`` with plain
    elementary children): only a *group* item tagged ``REDEFINES``, whose
    base is a plain elementary item with a quoted-string ``VALUE``
    literal, and whose own children are plain elementary items (no nested
    group child -- not evidenced anywhere in the corpus). An elementary
    item redefining another elementary item is captured on the AST/symbol
    (:attr:`~app.parser.semantic.symbols.VariableSymbol.redefines`) but
    has no children to derive here -- also unevidenced.

    Each REDEFINES group's *direct* elementary children are identified
    from the flat, declaration-ordered *symbols* list via the same
    level-number stack :func:`_resolve_array_occurs` already established
    -- COBOL's own nesting rule, not a heuristic, and not a second
    AST-walking mechanism (:class:`~app.parser.ast.data_items.GroupItemNode`
    never actually populates its own ``children`` tuple in this parser;
    every existing ancestor/descendant query in this backend already goes
    through the flat symbol list instead, and this one does too).

    Graceful degrade (documented, never fabricated) -- each case appends
    one ``BE013`` WARNING and contributes no entry for the affected
    child/children, leaving that Java field with no initializer, exactly
    the same fallback every other "no provably correct initializer" case
    in this backend already uses:

    * the base name does not resolve to a known symbol;
    * the base has no ``VALUE`` clause, or its value is not a
      quoted-string literal (a numeric base is not evidenced anywhere);
    * a child's own PICTURE width cannot be resolved (no ``cobol_type``,
      or it is itself a group) -- derivation stops for every remaining
      child of that group, since their offsets are no longer trustworthy;
    * a child's byte range would run past the end of the base's literal
      -- a genuine, flagged, corpus-level width inconsistency between the
      redefining group's own declared total size and the base item's,
      not invented by this function. Derivation stops there too, but
      every child fully *within* range keeps its correctly derived value.

    Args:
        symbols:
            Every :class:`~app.parser.semantic.symbols.VariableSymbol`,
            in COBOL declaration order (as
            :meth:`~app.parser.semantic.context.SymbolTable.all_symbols`
            already guarantees).
        diagnostics:
            Mutable list; ``BE013`` diagnostics appended on each degrade
            case.

    Returns:
        ``{CHILD_NAME: raw_value_literal}`` -- the same raw-literal-text
        shape :attr:`~app.parser.semantic.symbols.VariableSymbol.value`
        already uses (a numeric child's entry is a plain digit string,
        e.g. ``"02"``; an alphanumeric child's is single-quoted, e.g.
        ``"'SEDAN     '"``), fed through the exact same
        :func:`~app.backend.java.value_initializer.translate_value_literal`
        every other ``VALUE`` clause already goes through in
        :func:`build_fields_from_symbols` -- never a second initializer
        pipeline. A slice that is not actually valid for the child's own
        type (e.g. non-digit bytes sliced into a numeric child -- this
        corpus's own ``t_policy_redefines.cbl`` data is not always
        packed to align meaningfully with its own redefining views) is
        still returned here; ``translate_value_literal`` itself is the
        single place that already declines an unsafe literal, exactly as
        it would for a hand-written ``VALUE`` clause with the same text.
    """
    from app.parser.semantic.types import AlphanumericType, NumericType

    by_name: dict[str, VariableSymbol] = {s.name.upper(): s for s in symbols}

    # Immediate (one-level-up) parent of every non-condition-name symbol,
    # and that parent's direct children, via the identical level-number
    # stack technique _resolve_array_occurs uses above.
    children_of: dict[str, list[VariableSymbol]] = {}
    stack: list[tuple[int, str]] = []  # (level, upper-cased name)
    for sym in symbols:
        if sym.level == _CONDITION_NAME_LEVEL_FOR_STACK:
            continue
        while stack and stack[-1][0] >= sym.level:
            stack.pop()
        parent_name = stack[-1][1] if stack else None
        if parent_name is not None:
            children_of.setdefault(parent_name, []).append(sym)
        stack.append((sym.level, sym.name.upper()))

    result: dict[str, str] = {}

    for sym in symbols:
        if not sym.redefines:
            continue
        group_name = sym.name.upper()
        children = children_of.get(group_name, [])
        if not children:
            continue

        base = by_name.get(sym.redefines)
        if base is None:
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=(
                        f"REDEFINES base '{sym.redefines}' for '{sym.name}' "
                        "was not found; no derived values for its children."
                    ),
                    code="BE013",
                )
            )
            continue

        base_content = _quoted_string_content(base.value)
        if base_content is None:
            diagnostics.append(
                BackendDiagnostic(
                    severity=BackendSeverity.WARNING,
                    message=(
                        f"REDEFINES base '{base.name}' has no quoted-string "
                        f"VALUE literal; no derived values for '{sym.name}'"
                        "'s children."
                    ),
                    code="BE013",
                )
            )
            continue

        offset = 0
        for child in children:
            cobol_type = child.cobol_type
            width: int | None = None
            if isinstance(cobol_type, NumericType):
                width = cobol_type.digits
            elif isinstance(cobol_type, AlphanumericType):
                width = cobol_type.length

            if width is None:
                diagnostics.append(
                    BackendDiagnostic(
                        severity=BackendSeverity.WARNING,
                        message=(
                            f"REDEFINES child '{child.name}' of '{sym.name}' "
                            "has no resolvable PICTURE width; stopping "
                            "derivation for the remaining children."
                        ),
                        code="BE013",
                    )
                )
                break

            if offset + width > len(base_content):
                diagnostics.append(
                    BackendDiagnostic(
                        severity=BackendSeverity.WARNING,
                        message=(
                            f"REDEFINES group '{sym.name}' declared width "
                            f"exceeds base '{base.name}' size at "
                            f"'{child.name}' (needs bytes {offset}-"
                            f"{offset + width}, base has "
                            f"{len(base_content)}); stopping derivation "
                            "for the remaining children."
                        ),
                        code="BE013",
                    )
                )
                break

            slice_content = base_content[offset : offset + width]
            if isinstance(cobol_type, NumericType):
                result[child.name.upper()] = slice_content
            else:
                result[child.name.upper()] = f"'{slice_content}'"
            offset += width

    return result


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
    5. An **elementary** symbol (``NumericType``/``AlphanumericType``) that
       is itself, or is nested inside, a fixed ``OCCURS n`` item (task
       #stage33; see :func:`_resolve_array_occurs`) becomes a Java array:
       ``java_type`` gets a trailing ``"[]"`` and, when it would otherwise
       have no initializer, ``initial_value`` becomes ``"new <type>[n]"``.
       A COBOL ``VALUE`` clause on the item itself is deliberately **not**
       applied to the array (no per-element or fill-value semantics are
       invented — see :attr:`~app.backend.java.field_model.JavaField.occurs`);
       an item with both ``OCCURS`` and ``VALUE`` simply gets the plain
       ``new <type>[n]`` allocation, exactly as an ``OCCURS`` item with no
       ``VALUE`` does. A :class:`~app.parser.semantic.types.GroupType`
       symbol is **never** array-ified even when it has its own ``OCCURS``
       (e.g. ``05 LINE-ITEM OCCURS 5 TIMES.``) — only its elementary
       descendants are, since the group itself has no single Java type an
       array element could hold without a dedicated per-record class,
       which is out of this stage's scope.
    6. An elementary symbol that is a direct child of a ``REDEFINES``
       group (task #stage39) has no ``VALUE`` clause of its own in the
       evidenced corpus shape, but derives one from the redefined base
       item's own literal ``VALUE`` via :func:`_resolve_redefines_values`
       -- fed through step 3's identical ``translate_value_literal`` call,
       never a second initializer pipeline.

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
    array_occurs = _resolve_array_occurs(symbols)
    redefines_values = _resolve_redefines_values(symbols, diagnostics)

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

        # task #stage33: a fixed OCCURS elementary item (its own, or an
        # enclosing group's) becomes a Java array. Groups are deliberately
        # excluded -- see this function's own docstring, point 5.
        occurs = array_occurs.get(sym.name.upper())
        # task #stage39, point 6: a REDEFINES group's own child prefers
        # its derived literal over its own (always-absent, in the
        # evidenced shape) VALUE clause.
        literal = redefines_values.get(sym.name.upper(), sym.value)
        initial_value = translate_value_literal(literal, java_type)
        if occurs is not None and isinstance(
            cobol_type, (NumericType, AlphanumericType)
        ):
            element_type = java_type
            java_type = f"{element_type}[]"
            initial_value = f"new {element_type}[{occurs}]"
        else:
            occurs = None

        result.append(
            JavaField(
                java_name=java_name,
                java_type=java_type,
                initial_value=initial_value,
                cobol_name=sym.name,
                digits=digits,
                decimal_places=decimal_places,
                signed=signed,
                length=length,
                occurs=occurs,
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
    statements, paragraph_methods = _collect_statements(
        program, diagnostics, paragraph_order, context
    )
    outlined_java_names = {name for name, _ in paragraph_methods}

    # ------------------------------------------------------------------
    # 2b. Discover CALL/PERFORM targets that have no generated method body.
    #     Each becomes an empty ``private void`` stub so the class compiles,
    #     and each raises a BE009 WARNING so the missing body is not silently
    #     swallowed. (task #stage36: a PERFORM target whose real instructions
    #     were found in the IR is outlined into a genuine method instead --
    #     see `paragraph_methods` above -- and is excluded here so it is
    #     never *also* stubbed. Only a target that is still genuinely absent
    #     -- an external sub-program, or a name that resolves to no
    #     paragraph at all -- reaches this stub path.)
    # ------------------------------------------------------------------
    stub_targets = [
        (java_name, original, arg_count)
        for java_name, original, arg_count in _collect_call_targets(program)
        if java_name not in outlined_java_names
    ]
    for java_name, original, arg_count in stub_targets:
        params = ", ".join(f"Object arg{i}" for i in range(arg_count))
        diagnostics.append(
            BackendDiagnostic(
                severity=BackendSeverity.WARNING,
                message=(
                    f"CALL/PERFORM target '{original}' has no generated method "
                    f"body; emitting an empty stub 'private void "
                    f"{java_name}({params})'. The target is either an external "
                    "sub-program or a paragraph whose body is not present in "
                    "the IR; implement it in a follow-up task."
                ),
                code="BE009",
            )
        )

    # ------------------------------------------------------------------
    # 3. Render Java source
    # ------------------------------------------------------------------
    # The alphanumeric-equality helper is emitted only by a class that uses it.
    all_statement_lines = statements + [
        line for _, body in paragraph_methods for line in body
    ]
    helpers = (
        list(COBOL_EQUALS_HELPER)
        if any(f"{COBOL_EQUALS}(" in statement for statement in all_statement_lines)
        else []
    )
    source = _render_class(
        class_name,
        effective_fields,
        statements,
        stub_targets,
        helpers,
        paragraph_methods,
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
    from app.ir.instructions import IRIf, IRPerformUntil, IRPerformVarying

    closers = {
        IRIf: "IREndIf",
        IRPerformUntil: "IREndPerform",
        IRPerformVarying: "IREndPerform",
    }
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
) -> tuple[list[str], list[tuple[str, list[str]]]]:
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

    * :class:`~app.ir.instructions.IRIf`,
      :class:`~app.ir.instructions.IRPerformUntil`, or (task #stage34)
      :class:`~app.ir.instructions.IRPerformVarying` — emit header at
      current depth, then increment depth (body is one level deeper).
      ``IRPerformVarying`` -> Java ``for``, closed by the same
      ``IREndPerform`` an ``IRPerformUntil`` -> Java ``while`` is
      (COBOL's own ``END-PERFORM`` closes either form identically); see
      :func:`~app.backend.java.control_flow_emitter.emit_perform_varying`.
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

    task #stage36 -- ``PERFORM paragraph-name`` (and ``PERFORM ... THRU``):
    when the program contains no ``GO TO`` (the dispatcher above is inert)
    and at least one local ``PERFORM`` target's own instructions are present
    in the IR, the entry block is *not* lowered flat. Instead every
    paragraph is outlined into its own real Java method (see
    :func:`_collect_outlined_statements`), reusing this exact per-
    instruction lowering (:func:`_emit_instruction_list`) on each
    paragraph's own contiguous instruction slice instead of the whole flat
    list -- a real Java method call already gives ``PERFORM``'s call/return
    semantics for free, which the GO TO dispatcher's switch/``continue``
    model does not. This path and the GO TO dispatcher are mutually
    exclusive by construction (no corpus source uses both), so the
    dispatcher above is completely unaffected.

    Returns:
        ``(run_body_statements, paragraph_methods)``. ``run_body_statements``
        is the ordered list of Java statement strings for the ``run()``
        method body (control-flow headers/footers and body statements carry
        embedded depth prefixes; base 8-space ``main()`` indentation is
        applied later by :func:`_render_class`). ``paragraph_methods`` is a
        list of ``(java_method_name, body_statements)`` pairs for any
        ``PERFORM``-to-local-paragraph target outlined into a real method
        (task #stage36); empty when no outlining was needed, in which case
        ``run_body_statements`` is exactly what this function always
        produced before.
    """
    statements: list[str] = []
    if not program.modules:
        return statements, []
    module = program.modules[0]
    if not module.functions:
        return statements, []
    function = module.functions[0]
    if not function.blocks:
        return statements, []
    block = function.blocks[0]

    instructions = list(block.instructions)

    # GO TO dispatcher state (task #stage19); inert when `plan` is None.
    plan = _plan_dispatch(instructions, paragraph_order)

    if plan is None:
        ranges, order = _paragraph_ranges(instructions)
        perform_targets = _local_perform_targets(instructions, ranges)
        if perform_targets:
            return _collect_outlined_statements(
                instructions, diagnostics, context, ranges, order, perform_targets
            )

    statements, labels_at, labelled_upto = _emit_instruction_list(
        instructions, diagnostics, context, plan
    )

    if plan is None:
        return statements, []
    # Paragraphs after the last one with code (empty/unsupported) still need
    # their case label so a GO TO to them resolves.
    for case in range(labelled_upto + 1, len(plan[0])):
        labels_at.setdefault(len(statements), []).append(case)
    return _wrap_dispatch(statements, labels_at, plan[0]), []


def _emit_instruction_list(
    instructions: list[Any],
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None,
    plan: tuple[list[str], dict[str, int]] | None,
) -> tuple[list[str], dict[int, list[int]], int]:
    """
    Lower one contiguous, self-contained (depth-balanced) list of IR
    instructions into Java statement strings.

    This is :func:`_collect_statements`'s own per-instruction dispatch loop,
    extracted (task #stage36) so it can be reused verbatim on a single
    paragraph's (or ``PERFORM ... THRU`` range's) own instruction slice —
    see :func:`_collect_outlined_statements` — with exactly the same
    ``IRIf``/``IRElse``/``IREndIf``/``IRPerformUntil``/``IRPerformVarying``/
    ``IREndPerform``/``BE007``/``BE011`` handling as the flat/GO TO-dispatch
    path, never duplicated.

    ``depth``/``dead`` always start fresh (``0``/``[False]``): every
    *caller*-provided instruction slice is depth-balanced on its own (a
    COBOL paragraph's own ``IF``/``END-IF`` and ``PERFORM``/``END-PERFORM``
    never span a paragraph boundary), so no cross-slice state needs to be
    threaded through.

    Args:
        instructions: The instruction slice to lower (the whole flat block,
            or one paragraph's/THRU range's own contiguous sub-slice).
        diagnostics: Mutable list; diagnostics appended here.
        context: Optional condition context, as :func:`_collect_statements`.
        plan: The GO TO dispatch plan, or ``None`` — see
            :func:`_plan_dispatch`. Always ``None`` when *instructions* is a
            per-paragraph slice (task #stage36 and GO TO are mutually
            exclusive by corpus evidence).

    Returns:
        ``(statements, labels_at, labelled_upto)`` — ``labels_at``/
        ``labelled_upto`` are only meaningful when *plan* is not ``None``
        (empty/``-1`` otherwise) and are consumed by
        :func:`_collect_statements`'s ``_wrap_dispatch`` call.
    """
    # Local imports to avoid circular dependencies.
    from app.backend.java.control_flow_emitter import (
        emit_else as _emit_else,
        emit_end_if as _emit_end_if,
        emit_end_perform as _emit_end_perform,
        emit_if as _emit_if,
        emit_perform_until as _emit_perform_until,
        emit_perform_varying as _emit_perform_varying,
    )
    from app.backend.java.statement_emitter import emit_statement
    from app.ir.instructions import (
        IRElse,
        IREndIf,
        IREndPerform,
        IRIf,
        IRJump,
        IRPerformUntil,
        IRPerformVarying,
        IRReturn,
    )

    statements: list[str] = []
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
                    "STOP RUN/GOBACK earlier in the same generated method; "
                    "skipping to avoid generating invalid Java."
                ),
                code="BE011",
            )
        )

    skip_through = -1  # last index of an omitted (untranslatable) construct

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

            elif isinstance(instr, IRPerformVarying):
                if dead[depth]:
                    _skip_unreachable(type(instr).__name__)
                    depth += 1
                    dead.append(True)
                    continue
                stmts = _emit_perform_varying(instr, depth, diagnostics, context)
                if not stmts:
                    _omit_construct(index, "PERFORM VARYING", "loop body")
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
                                "IREndPerform encountered without a matching "
                                "IRPerformUntil/IRPerformVarying "
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

    return statements, labels_at, labelled_upto


def _paragraph_ranges(
    instructions: list[Any],
) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """
    Partition *instructions* into contiguous per-paragraph index ranges
    (task #stage36).

    Every instruction :meth:`~app.ir.builder.IRBuilder._emit` stamps with
    the enclosing paragraph's name (task #109); this groups the flat list
    back into ``UPPERCASED name -> (start, end)`` ranges (``instructions
    [start:end]`` is that paragraph's own contiguous slice) purely by
    watching that tag change, in source order — no new IR, no AST access.
    An instruction with no paragraph tag (only possible in a hand-built
    ``IRProgram``, e.g. in unit tests) is skipped: it belongs to no
    paragraph and is not part of any range.

    Returns:
        ``(ranges, order)`` — ``order`` is every distinct paragraph name,
        first-seen, in source order (matching :func:`_plan_dispatch`'s own
        collection); ``ranges`` maps each to its ``(start, end)`` pair.
    """
    ranges: dict[str, tuple[int, int]] = {}
    order: list[str] = []
    current: str | None = None
    start = 0
    for idx, instr in enumerate(instructions):
        name = (instr.paragraph or "").upper()
        if name != current:
            if current:
                ranges[current] = (start, idx)
            current = name
            start = idx
            if name and name not in order:
                order.append(name)
    if current:
        ranges[current] = (start, len(instructions))
    return ranges, order


def _local_perform_targets(
    instructions: list[Any], ranges: dict[str, tuple[int, int]]
) -> dict[tuple[str, str], tuple[str, str]]:
    """
    Collect every distinct local ``PERFORM`` target (task #stage36).

    Scans for every :class:`~app.ir.instructions.IRCall` tagged
    ``comment="PERFORM"`` (:meth:`~app.ir.builder.IRBuilder.build_perform_statement`)
    whose ``target`` resolves to a paragraph actually present in *ranges* —
    a real ``CALL`` (no ``"PERFORM"`` comment) or a ``PERFORM`` to a name
    that is not a local paragraph is deliberately excluded, so it keeps
    getting the ordinary ``BE009`` empty-stub treatment, unchanged.

    A ``PERFORM target THRU thru_target`` whose ``thru_target`` does *not*
    resolve to a local paragraph falls back to just ``target`` alone (its
    own range) — a defensive fallback for a shape no corpus source
    exercises (the one evidenced ``THRU`` occurrence resolves cleanly).

    Args:
        instructions: The whole flat instruction list (never a sub-slice —
            this must see every ``IRCall`` in the program).
        ranges: This program's paragraph ranges, from
            :func:`_paragraph_ranges`.

    Returns:
        ``{(target_upper, thru_upper_or_empty): (java_method_name,
        original_target_text)}``, one entry per distinct target/THRU pair
        actually invoked, in first-seen order.
    """
    from app.ir.instructions import IRCall

    targets: dict[tuple[str, str], tuple[str, str]] = {}
    for instr in instructions:
        if not isinstance(instr, IRCall) or instr.comment != "PERFORM":
            continue
        target = instr.target
        if not target:
            continue
        target_upper = target.upper()
        if target_upper not in ranges:
            continue
        thru_upper = ""
        if instr.thru_target and instr.thru_target.upper() in ranges:
            thru_upper = instr.thru_target.upper()
        key = (target_upper, thru_upper)
        if key not in targets:
            targets[key] = (to_java_field_name(target), target)
    return targets


def _collect_outlined_statements(
    instructions: list[Any],
    diagnostics: list[BackendDiagnostic],
    context: ConditionContext | None,
    ranges: dict[str, tuple[int, int]],
    order: list[str],
    perform_targets: dict[tuple[str, str], tuple[str, str]],
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """
    Lower a program that needs paragraph outlining (task #stage36).

    ``run()``'s body becomes the *first* paragraph's own instructions —
    COBOL execution starts at the first paragraph of PROCEDURE DIVISION,
    the same way the pre-#stage36 flat path already always began there.
    Every distinct local ``PERFORM`` target (:func:`_local_perform_targets`)
    becomes a real ``private void`` method: its body is that paragraph's own
    instruction slice, or — for ``PERFORM ... THRU`` — the single contiguous
    slice spanning from the target paragraph's first instruction to the
    THRU paragraph's last, lowered as one instruction list (COBOL's own
    THRU semantics: keep executing through the intervening paragraphs'
    instructions with no explicit fallthrough machinery needed, since they
    are already physically contiguous in the flat block).

    Each slice is lowered independently via :func:`_emit_instruction_list`
    (fresh ``depth``/``dead`` state, ``plan=None``) — the identical logic
    the flat path uses, just scoped to one paragraph/range instead of the
    whole block, so ``IF``/``PERFORM UNTIL``/``PERFORM VARYING``/``BE007``/
    ``BE011`` all behave exactly as documented for :func:`_collect_statements`.

    Returns:
        ``(run_body_statements, paragraph_methods)`` — see
        :func:`_collect_statements`.
    """
    if not order:
        statements, _, _ = _emit_instruction_list(
            instructions, diagnostics, context, None
        )
        return statements, []

    entry_start, entry_end = ranges[order[0]]
    run_body, _, _ = _emit_instruction_list(
        instructions[entry_start:entry_end], diagnostics, context, None
    )

    methods: list[tuple[str, list[str]]] = []
    seen_java_names: set[str] = set()
    for (target_upper, thru_upper), (java_name, _original) in perform_targets.items():
        if java_name in seen_java_names:
            continue
        seen_java_names.add(java_name)
        start = ranges[target_upper][0]
        end = ranges[thru_upper][1] if thru_upper else ranges[target_upper][1]
        body, _, _ = _emit_instruction_list(
            instructions[start:end], diagnostics, context, None
        )
        methods.append((java_name, body))

    return run_body, methods


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


def _collect_call_targets(program: IRProgram) -> list[tuple[str, str, int]]:
    """
    Collect CALL/PERFORM targets in the entry block that need a stub method.

    Scans the same entry basic block that :func:`_collect_statements` lowers
    and returns, for every :class:`~app.ir.instructions.IRCall`, the triple
    ``(java_method_name, original_target, arg_count)``.  The Java name is
    derived with exactly the same quote-stripping and
    :func:`to_java_field_name` conversion used by
    :func:`~app.backend.java.statement_emitter.emit_call`, so the stub
    method name is guaranteed to match the invocation the emitter produced.

    A CALL target in COBOL is either an external sub-program (``CALL "NAME"``)
    or, via PERFORM lowering, an internal paragraph. In both cases the current
    pipeline may provide no method body: external sub-programs are separately
    compiled units, and a paragraph whose own instructions are not present in
    the IR (task #stage36 -- e.g. its whole body is an unsupported statement
    like ``READ``) has nothing to outline into a real method either way.
    Emitting an empty ``private void`` stub keeps the generated class
    self-compiling without inventing behaviour or discarding the invocation.

    ``arg_count`` (task #stage36's own fix, found investigating this stage's
    corpus regressions) is ``len(instr.args)`` for the first occurrence of
    each target — needed because :func:`_render_class` was giving every stub
    a fixed zero-parameter signature regardless of how many arguments
    :func:`~app.backend.java.statement_emitter.emit_call` actually passes at
    the call site, a pre-existing, independent bug from CALL support itself,
    latent because no real external CALL with 1+ arguments had ever
    previously reached a compiled Java program: the paragraph carrying it
    was always itself either a top-level BE011 casualty or -- before that
    fix -- covered by this exact same always-empty-stub gap.

    Results preserve first-encountered order and are de-duplicated, so a
    target invoked twice yields a single stub (using the first occurrence's
    argument count -- COBOL does not vary a CALL/PERFORM target's own arity
    between call sites).

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` being lowered.

    Returns:
        An ordered, de-duplicated list of ``(java_name, original_target,
        arg_count)`` triples — one per distinct CALL/PERFORM target.
    """
    from app.ir.instructions import IRCall

    targets: list[tuple[str, str, int]] = []
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
        targets.append((java_name, target, len(instr.args)))

    return targets


def _render_class(
    class_name: str,
    fields: list[JavaField],
    statements: list[str],
    stub_targets: list[tuple[str, str, int]] | None = None,
    helpers: list[str] | None = None,
    paragraph_methods: list[tuple[str, list[str]]] | None = None,
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
            Optional list of ``(java_name, original_target, arg_count)``
            triples for CALL/PERFORM targets that need an empty ``private
            void`` stub method so the generated class compiles. ``arg_count``
            (task #stage36) gives the stub the same number of formal
            parameters the call site passes -- each typed ``Object`` so a
            ``String``/``int``/``double`` (autoboxed) argument compiles
            regardless of the target's real (unknowable, since it is never
            generated) parameter types -- so an arity mismatch never breaks
            compilation.
        helpers:
            Optional pre-indented lines of helper methods (such as the COBOL
            alphanumeric-equality helper) rendered after the stubs.
        paragraph_methods:
            Optional list of ``(java_name, body_statements)`` pairs (task
            #stage36) for a ``PERFORM``-to-local-paragraph target whose real
            instructions were found in the IR — each becomes a genuine
            ``private void`` method containing the paragraph's (or, for
            ``PERFORM ... THRU``, paragraph range's) own lowered statements,
            rendered *before* the empty stubs so a target is never both.

    Returns:
        A non-empty Java source string.
    """
    stubs = stub_targets or []
    methods = paragraph_methods or []
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

    # Real methods for PERFORM-to-local-paragraph targets whose own
    # instructions were found in the IR (task #stage36) — the paragraph's
    # (or PERFORM-THRU range's) actual lowered statements, not a stub.
    for java_name, body in methods:
        lines.append(f"    private void {java_name}() {{")
        lines.append("")
        for stmt in body:
            lines.append(f"        {stmt}")
        if body:
            lines.append("")
        lines.append("    }")
        lines.append("")

    # Empty stub methods for CALL/PERFORM targets that have no generated body,
    # so the class compiles.  Each carries a TODO naming the original target
    # and the BE009 diagnostic emitted alongside it. Declared with the same
    # number of (Object-typed) formal parameters the call site passes (task
    # #stage36), so a target invoked with arguments never fails to compile
    # with an arity mismatch merely because its own body is unavailable.
    for java_name, original, arg_count in stubs:
        params = ", ".join(f"Object arg{i}" for i in range(arg_count))
        lines.append(f"    private void {java_name}({params}) {{")
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
