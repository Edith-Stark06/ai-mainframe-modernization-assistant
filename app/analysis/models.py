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

from dataclasses import dataclass, field
from typing import Any

from app.ir.program import IRProgram
from app.parser.ast.program import ProgramNode
from app.analysis.dependencies.models import Dependency

__all__ = ["AnalysisCoverage", "AnalysisResult"]


@dataclass(frozen=True, slots=True)
class AnalysisCoverage:
    """
    How much of a COBOL source file the parser actually analysed.

    Task #108 exists because a file can produce ``success: True`` while
    the parser silently abandoned most of the PROCEDURE DIVISION — the
    original symptom this project was built to diagnose ("Insufficient
    data... Overall Readiness: 0.99" on a file that was mostly unparsed).
    This value type makes that distinction explicit and machine-readable
    instead of requiring a caller to notice a suspiciously small
    paragraph count.

    Attributes:
        tokens_total:
            Total tokens produced by the lexer for this file, including
            the trailing EOF sentinel.
        tokens_consumed:
            How many of those tokens the parser's cursor advanced past.
            Equal to ``tokens_total`` only when parsing reached EOF
            without being abandoned.
        paragraphs_parsed:
            Paragraphs that became
            :class:`~app.parser.ast.paragraphs.ParagraphNode` entries in
            the AST.
        statements_parsed:
            Total statements across all parsed paragraphs.
        unsupported_construct_count:
            Diagnostics whose
            :attr:`~app.parser.diagnostics.recovery.SyntaxDiagnostic.category`
            is ``UNSUPPORTED`` or ``UNMODELLED`` — valid COBOL this
            parser does not fully represent.
        abandoned_construct_count:
            Diagnostics whose category is ``ABANDONED`` — regions of
            source the parser stopped analysing entirely.
        is_complete:
            ``True`` only when every token was consumed and no
            abandonment was recorded.  This is the single field a caller
            should check before trusting that the AST represents the
            whole file.

    Note:
        There is no independent count of "paragraph labels present in
        the source regardless of parse success": computing one would
        mean re-implementing the parser's own label-recognition rule
        (word token immediately followed by a period, excluding known
        statement verbs) a second time outside the parser, which would
        drift out of sync with it.  ``tokens_consumed`` versus
        ``tokens_total``, together with ``abandoned_construct_count``,
        already gives a precise, duplication-free signal for "how much
        of the file was never reached" without that risk.

    Examples:
        >>> coverage = AnalysisCoverage(
        ...     tokens_total=100, tokens_consumed=100,
        ...     paragraphs_parsed=3,
        ...     statements_parsed=12, unsupported_construct_count=0,
        ...     abandoned_construct_count=0,
        ... )
        >>> coverage.is_complete
        True
    """

    tokens_total: int
    tokens_consumed: int
    paragraphs_parsed: int
    statements_parsed: int
    unsupported_construct_count: int
    abandoned_construct_count: int

    @property
    def is_complete(self) -> bool:
        """
        ``True`` if the parser consumed the whole file and abandoned nothing.

        Unsupported/unmodelled constructs (``SYN1xx``/``SYN2xx``) do not
        affect this flag: those are explicitly diagnosed and safely
        skipped, so the rest of the file is still trustworthy.
        Abandonment (``SYN3xx``) does affect it, because it means a
        region of source was never even inspected.

        Returns:
            ``True`` when ``tokens_consumed == tokens_total`` and
            ``abandoned_construct_count == 0``.
        """
        return (
            self.tokens_consumed >= self.tokens_total
            and self.abandoned_construct_count == 0
        )


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
            ``True`` if the analysis pipeline completed without semantic
            errors or unexpected exceptions, **and** coverage was
            complete (see :attr:`AnalysisCoverage.is_complete`).  A file
            that parses without exceptions but leaves a substantial
            region of PROCEDURE DIVISION source unanalysed is reported
            as ``success: False`` rather than silently claiming a
            complete analysis (task #108).
        error:
            The unexpected exception that caused failure, or ``None`` if the
            pipeline completed normally.
        ast:
            The parsed AST :class:`~app.parser.ast.program.ProgramNode`, or
            ``None`` if parsing did not complete.
        ir:
            The built IR :class:`~app.ir.program.IRProgram`, or ``None`` if
            IR construction did not complete.
        syntax_diagnostics:
            Diagnostics emitted by the syntax parser itself — syntax
            errors, unsupported constructs, unmodelled constructs, and
            abandoned regions.  Empty for results produced before parsing
            reached the parser stage.
        coverage:
            How much of the source file was actually analysed, or
            ``None`` if parsing did not complete far enough to measure
            it (e.g. a lexer failure).
    """

    java_source: str
    backend_diagnostics: list[Any]
    semantic_diagnostics: list[Any]
    success: bool
    dependencies: list[Dependency]
    error: Exception | None = None
    ast: ProgramNode | None = None
    ir: IRProgram | None = None
    syntax_diagnostics: list[Any] = field(default_factory=list)
    coverage: AnalysisCoverage | None = None
