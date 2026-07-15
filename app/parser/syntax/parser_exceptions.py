"""
Parser Exception Hierarchy.

Purpose:
    Provide the typed exception classes used by the COBOL Parser.
    Centralising parser exceptions here prevents circular imports and
    ensures that all parsing failures raise structured, typed errors.

Responsibilities:
    - Provide :class:`ParserError` as the root exception for all
      parser-phase failures.

Non-responsibilities:
    - Lexical analysis or scanning errors (see lexer_exceptions,
      scanner_exceptions).
    - Semantic analysis errors.

Dependencies:
    - Python standard library only.

Examples:
    Catching any parser error::

        from app.parser.syntax.parser_exceptions import ParserError

        try:
            ast = parser.parse(tokens)
        except ParserError as exc:
            print(f"Parse failed: {exc.message} at {exc.line}:{exc.column}")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

__all__ = ["ParserError"]


class ParserError(Exception):
    """
    Root exception for all COBOL parser failures.

    Raised when the parser encounters a token sequence that violates the
    COBOL grammar rules, or encounters any other fatal parsing condition.

    Attributes:
        message: Human-readable description of the failure.
        line:    One-based line number where the error occurred.
        column:  One-based column number where the error occurred.
        offset:  Zero-based absolute byte offset where the error occurred.

    Examples:
        >>> raise ParserError("unexpected token", line=3, column=5, offset=42)
        Traceback (most recent call last):
            ...
        app.parser.syntax.parser_exceptions.ParserError: unexpected token at 3:5
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
