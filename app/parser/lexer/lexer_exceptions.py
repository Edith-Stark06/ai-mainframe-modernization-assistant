"""
COBOL Lexer Exceptions.

Purpose:
    Define the typed exception classes raised by the
    :class:`~app.parser.lexer.lexer.CobolLexer`.  Keeping lexer
    exceptions in a dedicated module prevents circular imports and allows
    callers to catch lexer-specific failures independently.

Responsibilities:
    - Provide :class:`LexerError` as the root exception for all lexer
      failures.

Non-responsibilities:
    - Parsing, AST construction, or any COBOL semantic knowledge.

Dependencies:
    - Python standard library only.

Examples:
    Catching a lexer error::

        from app.parser.lexer.lexer_exceptions import LexerError

        try:
            tokens = lexer.tokenize(source)
        except LexerError as exc:
            print(f"Lexer failed: {exc.message}")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

__all__ = ["LexerError"]


class LexerError(Exception):
    """
    Raised when :class:`~app.parser.lexer.lexer.CobolLexer` encounters
    source text it cannot tokenise.

    This error is raised for:

    - Unterminated string literals (e.g. a ``"`` with no closing ``"``).
    - Characters that cannot be classified into any recognised token type.

    Attributes:
        message: Human-readable description of the failure.
        line:    One-based line number where the error occurred.
        column:  One-based column number where the error occurred.
        offset:  Zero-based absolute offset where the error occurred.

    Examples:
        >>> raise LexerError("unterminated string", line=3, column=5, offset=42)
        Traceback (most recent call last):
            ...
        app.parser.lexer.lexer_exceptions.LexerError: unterminated string at 3:5
    """

    def __init__(
        self,
        message: str,
        *,
        line: int = 0,
        column: int = 0,
        offset: int = 0,
    ) -> None:
        self.message = message
        self.line = line
        self.column = column
        self.offset = offset
        super().__init__(f"{message} at {line}:{column}")
