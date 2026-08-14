"""
Analysis Result Model.

Purpose:
    Provide :class:`AnalysisResult` — the immutable result object returned by
    :class:`~app.analysis.service.AnalysisService` after executing the full
    COBOL analysis pipeline.

Responsibilities:
    - Carry the parsed AST node.
    - Carry the built IR program.
    - Carry the generated Java source string.
    - Carry backend diagnostics from the Java generator.
    - Carry semantic diagnostics from the semantic analyser.
    - Indicate whether analysis succeeded.
    - Optionally carry the unexpected exception that caused failure.

Non-responsibilities:
    - Parser or lexer diagnostics (semantic diagnostics only).
    - AST / IR / Java source serialization.
    - Persistence or API exposure.

Dependencies:
    - :mod:`app.ir.program`                  — ``IRProgram``.
    - :mod:`app.parser.ast.program`          — ``ProgramNode``.
    - Python standard library only (``dataclasses``).

Examples:
    Result from a successful analysis::

        from app.analysis.models import AnalysisResult

        result = AnalysisResult(
            java_source="public class Hello { ... }",
            backend_diagnostics=[],
            semantic_diagnostics=[],
            success=True,
            ast=ProgramNode(...),
            ir=IRProgram(...),
        )
        result.success  # True

    Result from a failed analysis::

        result = AnalysisResult(
            java_source="",
            backend_diagnostics=[],
            semantic_diagnostics=[...],
            success=False,
            error=RuntimeError("boom"),
        )
        result.error  # RuntimeError("boom")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ir.program import IRProgram
from app.parser.ast.program import ProgramNode

__all__ = ["AnalysisResult"]


@dataclass
class AnalysisResult:
    """
    Result of a COBOL analysis pipeline execution.

    Attributes:
        java_source:
            The generated Java source string, or an empty string if analysis
            failed before code generation.
        backend_diagnostics:
            Diagnostics emitted by the Java backend during generation.
        semantic_diagnostics:
            Diagnostics emitted by the semantic analyser.
        success:
            ``True`` if the analysis pipeline completed without semantic errors
            or unexpected exceptions.
        error:
            The unexpected exception that caused failure, or ``None`` if the
            pipeline completed normally.
        ast:
            The parsed AST :class:`~app.parser.ast.program.ProgramNode`, or
            ``None`` if parsing did not complete.
        ir:
            The built IR :class:`~app.ir.program.IRProgram`, or ``None`` if
            IR construction did not complete.
    """

    java_source: str
    backend_diagnostics: list[Any]
    semantic_diagnostics: list[Any]
    success: bool
    error: Exception | None = None
    ast: ProgramNode | None = None
    ir: IRProgram | None = None
