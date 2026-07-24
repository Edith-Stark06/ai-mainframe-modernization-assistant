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
from typing import TYPE_CHECKING

from loguru import logger

from app.backend.java.field_model import JavaField
from app.backend.java.naming import to_java_field_name
from app.backend.java.type_mapper import map_cobol_type
from app.ir.printer import _format_instruction  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from app.ir.program import IRProgram
    from app.parser.semantic.symbols import VariableSymbol

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


def build_fields_from_symbols(
    symbols: list[VariableSymbol],
    diagnostics: list[BackendDiagnostic] | None = None,
) -> list[JavaField]:
    """
    Convert a list of :class:`~app.parser.semantic.symbols.VariableSymbol`
    objects into :class:`~app.backend.java.field_model.JavaField` objects.

    For each symbol:

    1. The COBOL name is converted to lowerCamelCase via
       :func:`~app.backend.java.naming.to_java_field_name`.
    2. The ``cobol_type`` is mapped to a Java type via
       :func:`~app.backend.java.type_mapper.map_cobol_type`.  Symbols without
       a type (``cobol_type is None``) are skipped with a ``BE003`` WARNING.
    3. The ``picture`` string is used as-is for the initial value when the
       symbol carries a ``VALUE`` clause (future enhancement; currently no
       initial value is set by this helper — callers can post-process the list).

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
    if diagnostics is None:
        diagnostics = []

    result: list[JavaField] = []

    for sym in symbols:
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

        result.append(
            JavaField(
                java_name=java_name,
                java_type=java_type,
                initial_value=None,
                cobol_name=sym.name,
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
    # 2. Collect entry-block instructions for stub comments
    # ------------------------------------------------------------------
    stubs = _collect_instruction_stubs(program)

    # ------------------------------------------------------------------
    # 3. Render Java source
    # ------------------------------------------------------------------
    source = _render_class(class_name, effective_fields, stubs)
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


def _collect_instruction_stubs(program: IRProgram) -> list[str]:
    """
    Return a list of comment strings — one per instruction in the first
    entry basic block of the first function of the first module.

    These stubs represent future statement lowering work.
    """
    stubs: list[str] = []
    if not program.modules:
        return stubs
    module = program.modules[0]
    if not module.functions:
        return stubs
    function = module.functions[0]
    if not function.blocks:
        return stubs
    block = function.blocks[0]

    for instr in block.instructions:
        try:
            stub = _format_instruction(instr)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            stub = type(instr).__name__
        stubs.append(stub)

    return stubs


def _render_class(
    class_name: str,
    fields: list[JavaField],
    stubs: list[str],
) -> str:
    """
    Render the complete Java class source string.

    Args:
        class_name:
            A valid Java identifier used as the class name.
        fields:
            List of :class:`~app.backend.java.field_model.JavaField` objects
            to emit as instance fields before the ``main`` method.
        stubs:
            Optional list of IR instruction descriptions; each is emitted
            as a ``// IR: <text>`` comment inside ``main``.

    Returns:
        A non-empty Java source string.
    """
    lines: list[str] = []

    # Class header
    lines.append(f"public class {class_name} {{")
    lines.append("")

    # Instance field declarations
    if fields:
        for java_field in fields:
            lines.append(java_field.render())
        lines.append("")

    # main method header
    lines.append("    public static void main(String[] args) {")
    lines.append("")

    # Instruction stub comments
    for stub in stubs:
        lines.append(f"        // IR: {stub}")

    if stubs:
        lines.append("")

    # main method footer
    lines.append("    }")
    lines.append("")

    # Class footer
    lines.append("}")
    lines.append("")

    return "\n".join(lines)
