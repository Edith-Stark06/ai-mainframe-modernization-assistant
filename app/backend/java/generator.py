"""
Java Class Generator.

Purpose:
    Translate an :class:`~app.ir.program.IRProgram` into a valid Java source
    string.

    The generator produces a deterministic Java class skeleton containing a
    ``public static void main(String[] args)`` entry-point method.  Statement
    generation is intentionally deferred to later tasks; this module establishes
    the backend foundation.

Design:
    The generation pipeline operates on the IR *without* accessing the COBOL
    AST or the ``SemanticContext`` directly.  All information required for
    class generation (program name, module name) is read from the IR program.

    Class naming follows these rules, applied in order:

    1. Use the first module's ``name`` field if non-empty.
    2. Fall back to the ``IRProgram.name`` field if non-empty.
    3. Fall back to the default ``"GeneratedProgram"`` if both are empty.

    The name is sanitised with :func:`_to_java_class_name` before use.

Responsibilities:
    - Derive a valid Java identifier for the class name from the IR.
    - Emit the class declaration, ``main`` method, and closing braces.
    - Emit a ``// IR: <instruction>`` comment stub for each instruction in the
      entry basic block (statement lowering is a future task).
    - Collect and return :class:`BackendDiagnostic` records for invalid IR
      (missing name, empty module list) without raising exceptions.
    - Return a non-empty string even when diagnostics are emitted.

Non-responsibilities:
    - Statement lowering (deferred to TASK-033+).
    - Variable declaration generation.
    - Spring Boot / Maven project generation.
    - Writing files to disk.
    - Optimisation.

Dependencies:
    - :mod:`app.ir.program`       — ``IRProgram``, ``IRModule``, ``IRFunction``.
    - :mod:`app.ir.blocks`        — ``IRBasicBlock``.
    - :mod:`app.ir.instructions`  — ``IRInstruction`` (for comment stubs).
    - :mod:`app.ir.printer`       — :func:`~app.ir.printer._format_instruction`
      (reused for comment text).
    - Python standard library only (``re``, ``dataclasses``).

Examples:
    Generating a Java class from a minimal IRProgram::

        from app.ir.program import IRProgram
        from app.backend.java.generator import generate

        ir = IRProgram(name="HELLO")
        java_src = generate(ir)
        assert "public class Hello" in java_src
        assert "public static void main" in java_src

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

from app.ir.printer import _format_instruction  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from app.ir.program import IRProgram

__all__ = [
    "BackendDiagnostic",
    "BackendSeverity",
    "GenerationResult",
    "generate",
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


def generate(program: IRProgram) -> str:
    """
    Generate a Java class string from *program*.

    This is the primary entry point for the Java backend.  It returns the
    generated Java source code directly.  Use :func:`generate_with_diagnostics`
    if you also need access to backend diagnostics.

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` to lower to Java.

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
    result = generate_with_diagnostics(program)
    for diag in result.diagnostics:
        logger.warning("JavaGenerator [{}] {}", diag.code, diag.message)
    return result.source


def generate_with_diagnostics(program: IRProgram) -> GenerationResult:
    """
    Generate Java source from *program* and return both the source and any
    diagnostics emitted during generation.

    Args:
        program:
            The :class:`~app.ir.program.IRProgram` to lower to Java.

    Returns:
        A :class:`GenerationResult` carrying the source string and any
        :class:`BackendDiagnostic` records.
    """
    diagnostics: list[BackendDiagnostic] = []

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
    source = _render_class(class_name, stubs)
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


def _render_class(class_name: str, stubs: list[str]) -> str:
    """
    Render the complete Java class source string.

    Args:
        class_name:
            A valid Java identifier used as the class name.
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
