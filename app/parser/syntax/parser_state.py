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
      diagnostic messages and future error-recovery.

Non-responsibilities:
    - Grammar logic (belongs in :mod:`app.parser.syntax.parser`).
    - AST construction.
    - Lexical analysis.

Dependencies:
    - :mod:`app.parser.lexer.token`          — ``Token``.
    - :mod:`app.parser.syntax.token_stream`  — ``TokenStream``.
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
        state.record_error()    # increments error_count

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.parser.lexer.token import Token
from app.parser.syntax.token_stream import TokenStream

__all__ = ["ParserState"]


class ParserState:
    """
    Mutable state container for a single parse run.

    A :class:`ParserState` wraps a :class:`~app.parser.syntax.token_stream.TokenStream`
    and adds an error counter so that the parser can accumulate errors
    without immediately aborting, enabling basic error-recovery in future
    tasks.

    Attributes:
        _stream:      The underlying :class:`TokenStream`.
        _error_count: Number of errors recorded during this parse run.

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
    # Error tracking
    # ------------------------------------------------------------------

    @property
    def error_count(self) -> int:
        """
        The number of parse errors recorded so far.

        Returns:
            Non-negative integer error count.
        """
        return self._error_count

    def record_error(self) -> None:
        """
        Increment the error counter by one.

        Call this whenever a recoverable parse error is encountered
        and the parser chooses to continue rather than raise immediately.
        """
        self._error_count += 1

    @property
    def has_errors(self) -> bool:
        """
        Return ``True`` if at least one error has been recorded.

        Returns:
            ``True`` when ``error_count > 0``.
        """
        return self._error_count > 0
