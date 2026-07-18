"""
Parser Error Recovery Utilities.

Purpose:
    Provide the diagnostic model and synchronisation helpers used by
    the COBOL recursive-descent parser to implement panic-mode error
    recovery.  When a grammar rule encounters a token it cannot handle,
    the recovery layer records a structured :class:`SyntaxDiagnostic`,
    advances the token stream to a known-safe *synchronisation point*,
    and returns control so that parsing can continue.

    Collecting multiple diagnostics in a single parse pass is the key
    user-facing benefit: rather than aborting at the first error,
    developers receive a full list of syntax problems in one run.

Responsibilities:
    - Define :class:`SyntaxDiagnostic` — a value type that carries
      error message, source location, and recovery context.
    - Define :class:`RecoveryContext` — an enum that names the grammar
      level at which recovery occurred.
    - Define :class:`SynchronisationPoint` — an enum that names the
      token class the parser synchronised on.
    - Implement :class:`RecoveryManager` — the stateful accumulator
      that parsers call to record errors and perform synchronisation.
    - Implement :func:`synchronise` — the low-level token-skip loop
      used by :class:`RecoveryManager`.

Non-responsibilities:
    - Semantic diagnostics (type mismatches, undefined names, etc.).
    - Warning-level diagnostics.
    - Automatic source correction or code completion.
    - IDE / LSP integration.

Dependencies:
    - :mod:`app.parser.lexer.position`   — ``Position`` value type.
    - :mod:`app.parser.lexer.token_types` — ``TokenType`` enumeration.
    - :mod:`app.parser.syntax.token_stream` — ``TokenStream``.
    - Python standard library only.

Examples:
    Recording a syntax error and synchronising to the next period::

        from app.parser.diagnostics.recovery import RecoveryManager
        from app.parser.syntax.token_stream import TokenStream

        manager = RecoveryManager()
        manager.record_and_synchronise(
            stream=stream,
            message="expected '.' after PROGRAM-ID name",
            error_token=stream.current(),
        )
        diagnostics = manager.diagnostics
        # list of SyntaxDiagnostic — one entry

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import TYPE_CHECKING

from app.parser.lexer.token_types import TokenType

if TYPE_CHECKING:
    from app.parser.lexer.token import Token
    from app.parser.syntax.token_stream import TokenStream

__all__ = [
    "RecoveryContext",
    "RecoveryManager",
    "SynchronisationPoint",
    "SyntaxDiagnostic",
    "synchronise",
]

# ---------------------------------------------------------------------------
# Synchronisation anchor token sets
# ---------------------------------------------------------------------------

#: Token types that the synchroniser will *stop at* (inclusive).
#: The parser resumes from the token **after** one of these is consumed.
_SYNC_TYPES: frozenset[TokenType] = frozenset(
    {
        TokenType.PERIOD,
        TokenType.EOF,
    }
)

#: Keyword lexemes that mark the beginning of a COBOL division header.
_DIVISION_KEYWORDS: frozenset[str] = frozenset(
    {
        "IDENTIFICATION",
        "ENVIRONMENT",
        "DATA",
        "PROCEDURE",
    }
)

#: Keyword lexemes that mark a section within a division.
_SECTION_KEYWORDS: frozenset[str] = frozenset(
    {
        "WORKING-STORAGE",
        "FILE",
        "LINKAGE",
        "LOCAL-STORAGE",
        "SCREEN",
        "REPORT",
        "COMMUNICATION",
    }
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


@unique
class SynchronisationPoint(Enum):
    """
    Identifies the token class the synchroniser anchored on.

    Members:
        PERIOD:
            Recovery halted at a ``.`` (period) token.
        DIVISION:
            Recovery halted at a COBOL division keyword such as
            ``IDENTIFICATION``, ``DATA``, or ``PROCEDURE``.
        SECTION:
            Recovery halted at a COBOL section keyword such as
            ``WORKING-STORAGE`` or ``LINKAGE``.
        PARAGRAPH:
            Recovery halted at what appears to be a paragraph label
            (an identifier or keyword immediately followed by a period).
        EOF:
            Recovery reached the end of the token stream without
            finding any other synchronisation anchor.

    Examples:
        >>> SynchronisationPoint.PERIOD.value
        'period'
    """

    PERIOD = "period"
    DIVISION = "division"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    EOF = "eof"


@unique
class RecoveryContext(Enum):
    """
    The grammar level at which error recovery was triggered.

    Members:
        IDENTIFICATION_DIVISION:
            Error occurred inside the IDENTIFICATION DIVISION parser.
        DATA_DIVISION:
            Error occurred inside the DATA DIVISION parser.
        PROCEDURE_DIVISION:
            Error occurred inside the PROCEDURE DIVISION parser.
        WORKING_STORAGE_SECTION:
            Error occurred while parsing the WORKING-STORAGE SECTION.
        PARAGRAPH:
            Error occurred inside a paragraph body.
        STATEMENT:
            Error occurred while parsing a statement.
        UNKNOWN:
            The recovery context was not specified by the caller.

    Examples:
        >>> RecoveryContext.DATA_DIVISION.value
        'data_division'
    """

    IDENTIFICATION_DIVISION = "identification_division"
    DATA_DIVISION = "data_division"
    PROCEDURE_DIVISION = "procedure_division"
    WORKING_STORAGE_SECTION = "working_storage_section"
    PARAGRAPH = "paragraph"
    STATEMENT = "statement"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Diagnostic value type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyntaxDiagnostic:
    """
    An immutable record of a single syntax error encountered during parsing.

    :class:`SyntaxDiagnostic` is a pure value type — it carries no
    references to mutable parser state and can be safely serialised,
    stored in sets, or compared for equality.

    Attributes:
        message:
            Human-readable description of the syntax error.
        line:
            One-based source line number where the error occurred.
        column:
            One-based source column number where the error occurred.
        offset:
            Zero-based absolute byte offset where the error occurred.
        filename:
            Name of the source file (empty string if unknown).
        context:
            The grammar level at which recovery was triggered
            (:class:`RecoveryContext`).
        sync_point:
            The synchronisation token that ended panic mode
            (:class:`SynchronisationPoint`), or ``None`` if recovery
            was not yet attempted when the diagnostic was created.
        tokens_skipped:
            Number of tokens consumed during synchronisation.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=3, column=5, offset=42, filename="x.cbl")
        >>> d = SyntaxDiagnostic(
        ...     message="expected '.'",
        ...     line=pos.line,
        ...     column=pos.column,
        ...     offset=pos.offset,
        ...     filename=pos.filename,
        ...     context=RecoveryContext.IDENTIFICATION_DIVISION,
        ...     sync_point=SynchronisationPoint.PERIOD,
        ...     tokens_skipped=2,
        ... )
        >>> d.line
        3
        >>> d.context
        <RecoveryContext.IDENTIFICATION_DIVISION: 'identification_division'>
    """

    message: str
    line: int
    column: int
    offset: int
    filename: str
    context: RecoveryContext
    sync_point: SynchronisationPoint | None
    tokens_skipped: int

    def __str__(self) -> str:
        """
        Return a human-readable one-line representation.

        Returns:
            A string in the form ``"<filename>:<line>:<column>: <message>"``.
        """
        location = f"{self.filename}:{self.line}:{self.column}"
        return f"{location}: {self.message}"


# ---------------------------------------------------------------------------
# Low-level synchronisation function
# ---------------------------------------------------------------------------


def synchronise(stream: TokenStream) -> tuple[SynchronisationPoint, int]:
    """
    Advance the token stream to the next safe synchronisation point.

    Implements panic-mode recovery: tokens are discarded until the
    synchroniser encounters one of:

    1. A **period** (``TokenType.PERIOD``) — consumed, then stop.
    2. A **division keyword** (e.g. ``IDENTIFICATION``, ``DATA``) —
       *not* consumed; the caller re-enters normal parsing from here.
    3. A **section keyword** (e.g. ``WORKING-STORAGE``) — *not*
       consumed; the caller re-enters normal parsing from here.
    4. A **paragraph label** — a non-statement identifier followed
       immediately by a period — the label token is **consumed** and
       the period is left in the stream for the caller to inspect.
    5. **EOF** — stop immediately.

    Args:
        stream:
            The active :class:`~app.parser.syntax.token_stream.TokenStream`.
            The cursor will be advanced past discarded tokens.

    Returns:
        A ``(SynchronisationPoint, tokens_skipped)`` tuple.
        *tokens_skipped* is the number of tokens consumed before the
        anchor was reached (period/EOF) or peeked (division/section/
        paragraph).

    Examples:
        >>> # Assumes stream is positioned on a bad token before a period.
        >>> sync_pt, skipped = synchronise(stream)
        >>> sync_pt
        <SynchronisationPoint.PERIOD: 'period'>
    """
    skipped: int = 0

    while not stream.eof():
        tok = stream.current()

        # ---- EOF ---------------------------------------------------
        if tok.type is TokenType.EOF:
            return SynchronisationPoint.EOF, skipped

        # ---- Period ------------------------------------------------
        if tok.type is TokenType.PERIOD:
            stream.advance()  # consume the period
            skipped += 1
            return SynchronisationPoint.PERIOD, skipped

        # ---- Division keyword (do NOT consume) ----------------------
        if tok.type is TokenType.KEYWORD:
            upper = tok.lexeme.upper()

            # Division boundary — peek ahead to confirm "X DIVISION"
            if upper in _DIVISION_KEYWORDS:
                next_tok = stream.peek()
                if (
                    next_tok.type is TokenType.KEYWORD
                    and next_tok.lexeme.upper() == "DIVISION"
                ):
                    return SynchronisationPoint.DIVISION, skipped

            # Section boundary
            if upper in _SECTION_KEYWORDS:
                return SynchronisationPoint.SECTION, skipped

        # ---- Paragraph label heuristic --------------------------------
        # A paragraph label is an IDENTIFIER or KEYWORD whose *next*
        # token is a PERIOD (the label terminator).
        #
        # Consume the current token before returning so that the
        # synchroniser always makes forward progress.  The period is
        # left in the stream so the calling grammar can inspect it and
        # recognise the paragraph boundary.
        if tok.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
            next_tok = stream.peek()
            if next_tok.type is TokenType.PERIOD:
                stream.advance()  # consume the label / bad token
                skipped += 1
                return SynchronisationPoint.PARAGRAPH, skipped

        # ---- Discard and continue -----------------------------------
        stream.advance()
        skipped += 1

    return SynchronisationPoint.EOF, skipped


# ---------------------------------------------------------------------------
# RecoveryManager
# ---------------------------------------------------------------------------


class RecoveryManager:
    """
    Stateful accumulator of syntax diagnostics for a single parse pass.

    :class:`RecoveryManager` is created once per parse run and injected
    into parser state.  Each time a recoverable syntax error is detected,
    the parser calls :meth:`record_and_synchronise`, which:

    1. Builds a :class:`SyntaxDiagnostic` from the error token and message.
    2. Calls :func:`synchronise` to advance the token stream to a safe
       restart position.
    3. Updates the diagnostic with the synchronisation result.
    4. Appends the completed diagnostic to the internal list.

    The parser then resumes from the synchronisation point, allowing
    further errors to be collected in the same pass.

    Attributes:
        _diagnostics:
            Ordered list of :class:`SyntaxDiagnostic` instances.
        _in_recovery:
            ``True`` while the synchroniser is active (used to prevent
            re-entrant recovery calls from nesting indefinitely).

    Examples:
        >>> manager = RecoveryManager()
        >>> manager.has_errors
        False
        >>> manager.error_count
        0
    """

    def __init__(self) -> None:
        """
        Initialise an empty recovery manager.

        The manager starts with no diagnostics and not in recovery mode.
        """
        self._diagnostics: list[SyntaxDiagnostic] = []
        self._in_recovery: bool = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def diagnostics(self) -> list[SyntaxDiagnostic]:
        """
        Return a copy of the collected diagnostics list.

        The list is ordered by the sequence in which errors were
        encountered during parsing.

        Returns:
            A new ``list[SyntaxDiagnostic]`` (defensive copy).

        Examples:
            >>> manager = RecoveryManager()
            >>> manager.diagnostics
            []
        """
        return list(self._diagnostics)

    @property
    def error_count(self) -> int:
        """
        Return the number of syntax errors recorded so far.

        Returns:
            Non-negative integer.

        Examples:
            >>> RecoveryManager().error_count
            0
        """
        return len(self._diagnostics)

    @property
    def has_errors(self) -> bool:
        """
        Return ``True`` if at least one diagnostic has been recorded.

        Returns:
            ``True`` when :attr:`error_count` > 0.

        Examples:
            >>> RecoveryManager().has_errors
            False
        """
        return bool(self._diagnostics)

    @property
    def in_recovery(self) -> bool:
        """
        Return ``True`` while the synchroniser is executing.

        This flag prevents re-entrant invocations of
        :meth:`record_and_synchronise` from causing infinite loops
        during catastrophic input sequences.

        Returns:
            ``True`` when the manager is actively synchronising.
        """
        return self._in_recovery

    def record_and_synchronise(
        self,
        stream: TokenStream,
        message: str,
        error_token: Token,
        context: RecoveryContext = RecoveryContext.UNKNOWN,
    ) -> SyntaxDiagnostic:
        """
        Record a syntax error and advance the stream to a safe point.

        This is the primary entry point that parser grammar rules call
        when they encounter an unexpected token.  The method is
        idempotent with respect to re-entrant calls: if recovery is
        already in progress (i.e. :attr:`in_recovery` is ``True``),
        the method records the error but does **not** attempt a nested
        synchronisation.

        Args:
            stream:
                The active token stream.  Tokens will be consumed until
                a synchronisation anchor is found.
            message:
                Human-readable description of the syntax error.
            error_token:
                The :class:`~app.parser.lexer.token.Token` that
                triggered the error.  Its position is recorded in the
                diagnostic.
            context:
                The :class:`RecoveryContext` identifying which grammar
                rule triggered recovery.  Defaults to
                :attr:`RecoveryContext.UNKNOWN`.

        Returns:
            The :class:`SyntaxDiagnostic` that was appended to the
            internal list.

        Examples:
            >>> diag = manager.record_and_synchronise(
            ...     stream=stream,
            ...     message="expected '.'",
            ...     error_token=bad_token,
            ...     context=RecoveryContext.IDENTIFICATION_DIVISION,
            ... )
            >>> manager.error_count
            1
        """
        pos = error_token.position

        if self._in_recovery:
            # Nested call — record the error but skip synchronisation
            # to avoid consuming tokens that the outer call will handle.
            diag = SyntaxDiagnostic(
                message=message,
                line=pos.line,
                column=pos.column,
                offset=pos.offset,
                filename=pos.filename,
                context=context,
                sync_point=None,
                tokens_skipped=0,
            )
            self._diagnostics.append(diag)
            return diag

        self._in_recovery = True
        try:
            sync_point, tokens_skipped = synchronise(stream)
        finally:
            self._in_recovery = False

        diag = SyntaxDiagnostic(
            message=message,
            line=pos.line,
            column=pos.column,
            offset=pos.offset,
            filename=pos.filename,
            context=context,
            sync_point=sync_point,
            tokens_skipped=tokens_skipped,
        )
        self._diagnostics.append(diag)
        return diag

    def record_error(
        self,
        message: str,
        error_token: Token,
        context: RecoveryContext = RecoveryContext.UNKNOWN,
        sync_point: SynchronisationPoint | None = None,
        tokens_skipped: int = 0,
    ) -> SyntaxDiagnostic:
        """
        Record a syntax error *without* consuming any tokens.

        Use this variant when the caller has already performed its own
        error-handling (e.g. skipping tokens manually) and only needs
        to register the diagnostic.

        Args:
            message:
                Human-readable description of the syntax error.
            error_token:
                The :class:`~app.parser.lexer.token.Token` that
                triggered the error.
            context:
                The :class:`RecoveryContext` identifying which grammar
                rule triggered the error.
            sync_point:
                The synchronisation point already found by the caller,
                or ``None``.
            tokens_skipped:
                Number of tokens the caller consumed during recovery.

        Returns:
            The :class:`SyntaxDiagnostic` that was appended.

        Examples:
            >>> diag = manager.record_error(
            ...     message="invalid level number 99",
            ...     error_token=tok,
            ...     context=RecoveryContext.DATA_DIVISION,
            ...     sync_point=SynchronisationPoint.PERIOD,
            ...     tokens_skipped=3,
            ... )
            >>> manager.error_count
            1
        """
        pos = error_token.position
        diag = SyntaxDiagnostic(
            message=message,
            line=pos.line,
            column=pos.column,
            offset=pos.offset,
            filename=pos.filename,
            context=context,
            sync_point=sync_point,
            tokens_skipped=tokens_skipped,
        )
        self._diagnostics.append(diag)
        return diag
