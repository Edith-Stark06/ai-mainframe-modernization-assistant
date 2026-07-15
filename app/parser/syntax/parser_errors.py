"""
Extended Parser Error Hierarchy.

Purpose:
    Provide concrete exception subclasses that give the parser precise,
    typed error conditions beyond the root :class:`ParserError`.
    Keeping them in a dedicated module prevents circular imports and
    makes the error taxonomy easy to extend in future tasks.

Responsibilities:
    - Provide :class:`UnexpectedTokenError` for token-mismatch failures.
    - Provide :class:`UnexpectedEOFError` for premature end-of-input.
    - Both inherit from :class:`~app.parser.syntax.parser_exceptions.ParserError`
      so callers can catch the base class when they do not need fine-
      grained error discrimination.

Non-responsibilities:
    - Semantic or type-checking errors.
    - Lexical errors (see :mod:`app.parser.lexer.lexer_exceptions`).

Dependencies:
    - :mod:`app.parser.syntax.parser_exceptions` — ``ParserError`` base.
    - :mod:`app.parser.lexer.token_types`        — ``TokenType``.
    - Python standard library only.

Examples:
    Raising an unexpected-token error::

        from app.parser.syntax.parser_errors import UnexpectedTokenError
        from app.parser.lexer.token_types import TokenType

        raise UnexpectedTokenError(
            found_lexeme="MOVE",
            found_type=TokenType.KEYWORD,
            expected_type=TokenType.PERIOD,
            line=10,
            column=5,
            offset=200,
        )

    Raising an unexpected-EOF error::

        from app.parser.syntax.parser_errors import UnexpectedEOFError

        raise UnexpectedEOFError(line=42, column=1, offset=999)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.parser.syntax.parser_exceptions import ParserError

if TYPE_CHECKING:
    from app.parser.lexer.token_types import TokenType

__all__ = ["UnexpectedEOFError", "UnexpectedTokenError"]


class UnexpectedTokenError(ParserError):
    """
    Raised when the parser encounters a token it did not expect.

    This is the most common parse error: the grammar rule currently being
    matched required a specific :class:`~app.parser.lexer.token_types.TokenType`
    (or lexeme), but the next token in the stream was something different.

    Attributes:
        found_lexeme:
            The raw text of the offending token as it appeared in the
            source file.
        found_type:
            The :class:`~app.parser.lexer.token_types.TokenType` of the
            offending token.
        expected_type:
            The :class:`~app.parser.lexer.token_types.TokenType` that the
            parser was expecting, or ``None`` if multiple types were
            acceptable.

    Examples:
        >>> from app.parser.lexer.token_types import TokenType
        >>> err = UnexpectedTokenError(
        ...     found_lexeme="MOVE",
        ...     found_type=TokenType.KEYWORD,
        ...     expected_type=TokenType.PERIOD,
        ...     line=3,
        ...     column=7,
        ...     offset=50,
        ... )
        >>> err.found_lexeme
        'MOVE'
        >>> err.found_type
        <TokenType.KEYWORD: 'keyword'>
    """

    def __init__(
        self,
        found_lexeme: str,
        found_type: TokenType,
        *,
        expected_type: TokenType | None = None,
        line: int = 0,
        column: int = 0,
        offset: int = 0,
    ) -> None:
        self.found_lexeme = found_lexeme
        self.found_type = found_type
        self.expected_type = expected_type

        if expected_type is not None:
            message = (
                f"unexpected token {found_lexeme!r} "
                f"(got {found_type.value!r}, expected {expected_type.value!r})"
            )
        else:
            message = f"unexpected token {found_lexeme!r} (type {found_type.value!r})"

        super().__init__(message, line=line, column=column, offset=offset)


class UnexpectedEOFError(ParserError):
    """
    Raised when the token stream ends before the grammar rule is complete.

    The parser was still in the middle of matching a rule when it reached
    the ``EOF`` sentinel, meaning the source file is syntactically
    incomplete.

    Examples:
        >>> err = UnexpectedEOFError(line=100, column=1, offset=4096)
        >>> "EOF" in str(err)
        True
        >>> isinstance(err, UnexpectedEOFError)
        True
    """

    def __init__(
        self,
        *,
        line: int = 0,
        column: int = 0,
        offset: int = 0,
    ) -> None:
        super().__init__(
            "unexpected end of file",
            line=line,
            column=column,
            offset=offset,
        )
