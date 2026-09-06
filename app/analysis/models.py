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
    How much of a COBOL source file the *parser* actually traversed.

    Task #108 exists because a file can produce ``success: True`` while
    the parser silently abandoned most of the PROCEDURE DIVISION — the
    original symptom this project was built to diagnose ("Insufficient
    data... Overall Readiness: 0.99" on a file that was mostly unparsed).
    This value type makes that distinction explicit and machine-readable
    instead of requiring a caller to notice a suspiciously small
    paragraph count.

    Scope warning -- read before using :attr:`parse_complete`:
        Every field here, including :attr:`parse_complete`, describes
        **parser coverage**: how far the parser's cursor travelled
        through the token stream, and whether it gave up on any region
        along the way. None of it describes **semantic or AST
        completeness**. A file can have ``parse_complete = True`` while
        its AST is missing real information, because #108's own
        unsupported/unmodelled diagnostics (``SYN1xx``/``SYN2xx``) exist
        precisely for constructs the parser reaches, recognises, and
        then explicitly declines to represent -- COMP-3 clauses, OPEN
        statements, and the like. Whether the AST is a *complete*
        representation of the source is a #109 (AST/IR completeness)
        question this type does not answer. Do not read
        ``parse_complete: True`` as "the AST fully represents this
        file" -- read it as "the parser did not abandon any region of
        this file."

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
            is ``UNSUPPORTED`` or ``UNMODELLED`` — valid COBOL the parser
            reached and recognised but does not represent in the AST.
            These do **not** count as abandonment: the parser kept going
            and diagnosed the gap explicitly, so this number measures
            known, reported limitations, not lost coverage.
        abandoned_construct_count:
            Diagnostics whose category is ``ABANDONED`` — regions of
            source the parser stopped analysing entirely, with no
            diagnostic previously identifying what was in them.
        parse_complete:
            ``True`` only when the parser's cursor consumed every token
            and no abandonment was recorded. This says the parser did
            not give up on any region of the file -- it says nothing
            about whether every construct the parser passed through is
            represented in the AST. See the scope warning above.

    Note:
        There is no independent count of "paragraph labels present in
        the source regardless of parse success": computing one would
        mean re-implementing the parser's own label-recognition rule
        (word token immediately followed by a period, excluding known
        statement verbs) a second time outside the parser, which would
        drift out of sync with it.  ``tokens_consumed`` versus
        ``tokens_total``, together with ``abandoned_construct_count``,
        already gives a precise, duplication-free signal for "how much
        of the file the parser's cursor never reached" without that risk.

    Examples:
        >>> coverage = AnalysisCoverage(
        ...     tokens_total=100, tokens_consumed=100,
        ...     paragraphs_parsed=3,
        ...     statements_parsed=12, unsupported_construct_count=0,
        ...     abandoned_construct_count=0,
        ... )
        >>> coverage.parse_complete
        True
    """

    tokens_total: int
    tokens_consumed: int
    paragraphs_parsed: int
    statements_parsed: int
    unsupported_construct_count: int
    abandoned_construct_count: int
    unknown_token_count: int = 0
    """
    Tokens the lexer emitted with type ``UNKNOWN`` — source text it could
    not classify. Added for Phase 5 lexical coverage (#115); defaults to
    ``0`` so existing constructions and the ``parse_complete`` contract
    are unaffected. Does **not** feed ``parse_complete`` (which is a
    parser-cursor signal, not a lexical one).
    """

    @property
    def parse_complete(self) -> bool:
        """
        ``True`` if the parser's cursor consumed the whole file and
        abandoned no region of it.

        This is a **parser-coverage** signal, not a semantic- or
        AST-completeness one -- see the scope warning on this class.
        Unsupported/unmodelled constructs (``SYN1xx``/``SYN2xx``) do not
        affect this flag: those are explicitly diagnosed and safely
        skipped, so the parser's cursor still reaches everything after
        them. Abandonment (``SYN3xx``) does affect it, because it means
        a region of source was never even inspected by the parser.

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
            errors or unexpected exceptions, **and** the parser did not
            abandon any region of the source (see
            :attr:`AnalysisCoverage.parse_complete`).  A file that parses
            without exceptions but leaves a substantial region of
            PROCEDURE DIVISION source unanalysed is reported as
            ``success: False`` rather than silently claiming a clean
            result (task #108).

            ``success: True`` does **not** mean the AST completely
            represents the COBOL source.  Explicitly diagnosed
            unsupported/unmodelled constructs (see
            :attr:`syntax_diagnostics`) do not by themselves make
            ``success`` ``False`` — they are known, reported gaps in AST
            representation, not abandonment, and whether the AST is a
            *complete* representation of the file is a #109 (AST/IR
            completeness) question this flag does not answer.  Check
            :attr:`coverage` and :attr:`syntax_diagnostics` for that
            picture; do not infer AST completeness from ``success``
            alone.
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
            How much of the source file the *parser* actually traversed
            (see :class:`AnalysisCoverage`'s scope warning: this is
            parser coverage, not semantic or AST completeness), or
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
