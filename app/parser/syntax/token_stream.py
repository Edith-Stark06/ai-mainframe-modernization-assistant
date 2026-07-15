"""
Token Stream.

Purpose:
    Provide a safe, cursor-based abstraction over a flat list of lexer
    tokens.  The parser navigates the token sequence exclusively through
    this class; it never manipulates the raw token list directly.

    Centralising navigation here gives us a single place to enforce
    bounds-checking, lookahead, and error-position reporting.

Responsibilities:
    - Maintain an internal cursor index into the token list.
    - Expose :meth:`current` — the token at the cursor.
    - Expose :meth:`peek` — look ahead without advancing.
    - Expose :meth:`advance` — consume and return the current token.
    - Expose :meth:`eof` — signal when the stream is exhausted.
    - Expose :meth:`expect` — advance and raise
      :class:`~app.parser.syntax.parser_errors.UnexpectedTokenError`
      or :class:`~app.parser.syntax.parser_errors.UnexpectedEOFError`
      on mismatch.

Non-responsibilities:
    - Grammar rules or parsing logic.
    - AST construction.
    - Lexical analysis.

Dependencies:
    - :mod:`app.parser.lexer.token`      — ``Token``.
    - :mod:`app.parser.lexer.token_types` — ``TokenType``.
    - :mod:`app.parser.syntax.parser_errors` — typed error classes.
    - Python standard library only.

Examples:
    Basic navigation::

        from app.parser.syntax.token_stream import TokenStream
        from app.parser.lexer.token import Token
        from app.parser.lexer.token_types import TokenType
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        eof = Token(type=TokenType.EOF, lexeme="", position=pos)
        stream = TokenStream([eof])

        stream.eof()          # True
        stream.current()      # Token(EOF, ...)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_errors import UnexpectedEOFError, UnexpectedTokenError

__all__ = ["TokenStream"]


class TokenStream:
    """
    Cursor-based view over a flat sequence of lexer tokens.

    The :class:`TokenStream` wraps a ``list[Token]`` and exposes only
    the navigation primitives the parser requires.  All bounds-checking
    and mismatch-detection is encapsulated here so that grammar rules
    can be written without defensive indexing code.

    The stream expects the token list to end with exactly one
    ``TokenType.EOF`` sentinel.  Advancing past that sentinel keeps the
    cursor pointing at the EOF token — the stream never goes out of
    bounds.

    Attributes:
        _tokens: The immutable token sequence (stored as a tuple).
        _pos:    Current zero-based cursor index.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> from app.parser.lexer.token import Token
        >>> from app.parser.lexer.token_types import TokenType
        >>> pos = Position(line=1, column=1, offset=0, filename="t.cbl")
        >>> eof = Token(type=TokenType.EOF, lexeme="", position=pos)
        >>> stream = TokenStream([eof])
        >>> stream.eof()
        True
    """

    def __init__(self, tokens: list[Token]) -> None:
        """
        Initialise the stream from a list of tokens.

        Args:
            tokens:
                A non-empty list of :class:`~app.parser.lexer.token.Token`
                objects ending with a ``TokenType.EOF`` sentinel.

        Raises:
            ValueError: If *tokens* is empty.
        """
        if not tokens:
            raise ValueError("TokenStream requires at least one token (EOF sentinel).")
        self._tokens: tuple[Token, ...] = tuple(tokens)
        self._pos: int = 0

    # ------------------------------------------------------------------
    # Navigation primitives
    # ------------------------------------------------------------------

    def current(self) -> Token:
        """
        Return the token at the current cursor position.

        The cursor always points to a valid token; when exhausted it
        remains on the final EOF sentinel.

        Returns:
            The :class:`~app.parser.lexer.token.Token` at the cursor.
        """
        return self._tokens[self._pos]

    def peek(self, offset: int = 1) -> Token:
        """
        Return the token *offset* positions ahead without advancing.

        If the look-ahead index exceeds the token list, the EOF
        sentinel is returned so callers never see an out-of-bounds
        error.

        Args:
            offset:
                How many positions ahead to look (default ``1``).
                Must be ≥ 0.

        Returns:
            The token at ``cursor + offset``, or the EOF token when
            the look-ahead is past the end of the stream.
        """
        target = self._pos + offset
        if target >= len(self._tokens):
            return self._tokens[-1]  # always EOF
        return self._tokens[target]

    def advance(self) -> Token:
        """
        Consume and return the current token, then move the cursor forward.

        If the cursor is already at EOF the EOF token is returned and
        the cursor stays in place (idempotent at end-of-stream).

        Returns:
            The token that was current before advancing.
        """
        token = self._tokens[self._pos]
        if self._pos < len(self._tokens) - 1:
            self._pos += 1
        return token

    def eof(self) -> bool:
        """
        Return ``True`` when the current token is the EOF sentinel.

        Returns:
            ``True`` if the stream is exhausted, ``False`` otherwise.
        """
        return self._tokens[self._pos].type is TokenType.EOF

    # ------------------------------------------------------------------
    # Guarded consumption
    # ------------------------------------------------------------------

    def expect(self, token_type: TokenType) -> Token:
        """
        Consume the current token if its type matches *token_type*.

        Args:
            token_type:
                The :class:`~app.parser.lexer.token_types.TokenType`
                that the current token must have.

        Returns:
            The consumed :class:`~app.parser.lexer.token.Token`.

        Raises:
            UnexpectedEOFError:
                If the current token is the EOF sentinel and
                *token_type* is not ``TokenType.EOF``.
            UnexpectedTokenError:
                If the current token's type does not match *token_type*.
        """
        token = self.current()

        if token.type is TokenType.EOF and token_type is not TokenType.EOF:
            raise UnexpectedEOFError(
                line=token.position.line,
                column=token.position.column,
                offset=token.position.offset,
            )

        if token.type is not token_type:
            raise UnexpectedTokenError(
                found_lexeme=token.lexeme,
                found_type=token.type,
                expected_type=token_type,
                line=token.position.line,
                column=token.position.column,
                offset=token.position.offset,
            )

        return self.advance()

    # ------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------

    @property
    def position(self) -> int:
        """
        Return the current zero-based cursor index.

        Returns:
            Current cursor position as an integer.
        """
        return self._pos

    def __len__(self) -> int:
        """Return the total number of tokens including the EOF sentinel."""
        return len(self._tokens)
