"""
Parser State.

Purpose:
    Encapsulate the mutable bookkeeping state of the COBOL recursive
    descent parser.  Separating state from grammar rules keeps each
    grammar method focused on structure and makes the overall parser
    easier to test and reason about.

Responsibilities:
    - Track the number of parse errors encountered.
    - Expose the current :class:`~app.parser.lexer.token.Token` via
      the wrapped :class:`~app.parser.syntax.token_stream.TokenStream`.
    - Record the parser's conceptual ``position`` (cursor index) for
      diagnostic messages and error-recovery.
    - Maintain a :class:`~app.parser.diagnostics.recovery.RecoveryManager`
      for collecting structured :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic`
      records and performing panic-mode synchronisation.
    - Expose helpers that delegate to the recovery manager so that
      grammar rules need only hold a reference to :class:`ParserState`.

Non-responsibilities:
    - Grammar logic (belongs in :mod:`app.parser.syntax.parser`).
    - AST construction.
    - Lexical analysis.

Dependencies:
    - :mod:`app.parser.lexer.token`                     — ``Token``.
    - :mod:`app.parser.syntax.token_stream`             — ``TokenStream``.
    - :mod:`app.parser.diagnostics.recovery`            — ``RecoveryManager``,
      ``SyntaxDiagnostic``, ``RecoveryContext``.
    - Python standard library only.

Examples:
    Creating and interrogating a ParserState::

        from app.parser.syntax.parser_state import ParserState
        from app.parser.syntax.token_stream import TokenStream

        stream = TokenStream(tokens)
        state = ParserState(stream)

        state.current_token     # the current Token
        state.position          # cursor index (int)
        state.error_count       # 0 initially
        state.record_error()    # increments legacy error_count
        state.diagnostics       # list[SyntaxDiagnostic]

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.parser.diagnostics.recovery import (
    RecoveryContext,
    RecoveryManager,
    SyntaxDiagnostic,
)
from app.parser.lexer.token import Token
from app.parser.syntax.token_stream import TokenStream

__all__ = ["ParserState"]


class ParserState:
    """
    Mutable state container for a single parse run.

    A :class:`ParserState` wraps a :class:`~app.parser.syntax.token_stream.TokenStream`
    and adds:

    * A legacy ``error_count`` integer for backward-compatible callers.
    * A :class:`~app.parser.diagnostics.recovery.RecoveryManager` that
      collects structured :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic`
      records and performs panic-mode token synchronisation.

    Grammar rules interact exclusively with :class:`ParserState` — they
    never hold a direct reference to the stream or the recovery manager.

    Attributes:
        _stream:
            The underlying :class:`TokenStream`.
        _error_count:
            Number of legacy errors recorded during this parse run.
        _recovery:
            The :class:`RecoveryManager` for this parse pass.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> from app.parser.lexer.token import Token
        >>> from app.parser.lexer.token_types import TokenType
        >>> from app.parser.syntax.token_stream import TokenStream
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> eof = Token(type=TokenType.EOF, lexeme="", position=pos)
        >>> state = ParserState(TokenStream([eof]))
        >>> state.error_count
        0
        >>> state.has_errors
        False
    """

    def __init__(self, stream: TokenStream) -> None:
        """
        Initialise the state with a token stream.

        Args:
            stream:
                The :class:`~app.parser.syntax.token_stream.TokenStream`
                that this state will monitor.
        """
        self._stream: TokenStream = stream
        self._error_count: int = 0
        self._recovery: RecoveryManager = RecoveryManager()

    # ------------------------------------------------------------------
    # Token access (delegates to TokenStream)
    # ------------------------------------------------------------------

    @property
    def current_token(self) -> Token:
        """
        The token at the current cursor position.

        Returns:
            The current :class:`~app.parser.lexer.token.Token`.
        """
        return self._stream.current()

    @property
    def position(self) -> int:
        """
        The zero-based cursor index within the token stream.

        Returns:
            Current cursor index as an integer.
        """
        return self._stream.position

    @property
    def stream(self) -> TokenStream:
        """
        The underlying :class:`~app.parser.syntax.token_stream.TokenStream`.

        Grammar rules in the parser use this to navigate the token
        sequence without holding a direct reference to the stream.

        Returns:
            The wrapped :class:`TokenStream`.
        """
        return self._stream

    # ------------------------------------------------------------------
    # Legacy error tracking (backward-compatible)
    # ------------------------------------------------------------------

    @property
    def error_count(self) -> int:
        """
        The number of parse errors recorded so far.

        Includes both legacy errors (via :meth:`record_error`) and
        structured diagnostics (via :meth:`record_and_synchronise`).

        Returns:
            Non-negative integer error count.
        """
        return self._error_count + self._recovery.error_count

    def record_error(self) -> None:
        """
        Increment the legacy error counter by one.

        Call this when a recoverable parse error is encountered and the
        parser chooses to continue rather than raise immediately, but no
        structured diagnostic is needed (e.g. in existing grammar rules
        that predate the recovery system).

        For new code, prefer :meth:`record_and_synchronise` which
        creates a full :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic`.
        """
        self._error_count += 1

    @property
    def has_errors(self) -> bool:
        """
        Return ``True`` if at least one error has been recorded.

        Covers both legacy errors and structured diagnostics.

        Returns:
            ``True`` when ``error_count > 0``.
        """
        return self.error_count > 0

    # ------------------------------------------------------------------
    # Structured diagnostic collection
    # ------------------------------------------------------------------

    @property
    def recovery_manager(self) -> RecoveryManager:
        """
        Return the :class:`~app.parser.diagnostics.recovery.RecoveryManager`
        for this parse run.

        Grammar rules that need fine-grained control over recovery
        (e.g. to inspect :attr:`~app.parser.diagnostics.recovery.RecoveryManager.in_recovery`)
        may access the manager directly via this property.

        Returns:
            The active :class:`RecoveryManager`.
        """
        return self._recovery

    @property
    def diagnostics(self) -> list[SyntaxDiagnostic]:
        """
        Return a copy of all structured diagnostics collected so far.

        Returns:
            A new ``list[SyntaxDiagnostic]`` ordered by encounter time.
        """
        return self._recovery.diagnostics

    def record_and_synchronise(
        self,
        message: str,
        error_token: Token,
        context: RecoveryContext = RecoveryContext.UNKNOWN,
    ) -> SyntaxDiagnostic:
        """
        Record a syntax error and advance the stream to a safe point.

        Delegates to
        :meth:`~app.parser.diagnostics.recovery.RecoveryManager.record_and_synchronise`.
        Grammar rules should call this method instead of accessing the
        recovery manager directly.

        Args:
            message:
                Human-readable description of the syntax error.
            error_token:
                The :class:`~app.parser.lexer.token.Token` that
                triggered the error; its :attr:`position` is recorded.
            context:
                The :class:`RecoveryContext` identifying which grammar
                rule triggered recovery.

        Returns:
            The :class:`SyntaxDiagnostic` that was appended.

        Examples:
            >>> diag = state.record_and_synchronise(
            ...     message="expected '.' after IDENTIFICATION DIVISION",
            ...     error_token=state.current_token,
            ...     context=RecoveryContext.IDENTIFICATION_DIVISION,
            ... )
        """
        return self._recovery.record_and_synchronise(
            stream=self._stream,
            message=message,
            error_token=error_token,
            context=context,
        )

    @property
    def in_recovery(self) -> bool:
        """
        Return ``True`` while panic-mode synchronisation is in progress.

        Grammar rules can inspect this to avoid emitting spurious nested
        errors during a recovery sequence.

        Returns:
            ``True`` when the recovery manager is actively synchronising.
        """
        return self._recovery.in_recovery
