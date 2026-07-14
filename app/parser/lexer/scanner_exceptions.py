"""
Character Scanner Exceptions.

Purpose:
    Define the typed exception classes raised by the
    :class:`~app.parser.lexer.scanner.CharacterScanner`.  Keeping scanner
    exceptions in a dedicated module prevents circular imports and allows
    callers to catch scanner-specific failures independently of the broader
    parser exception hierarchy.

Responsibilities:
    - Provide :class:`ScannerError` as the root exception for all
      character-scanner failures.

Non-responsibilities:
    - Lexing, parsing, or any COBOL semantic knowledge.
    - Normalisation errors (see :mod:`app.parser.lexer.exceptions`).

Dependencies:
    - Python standard library only.

Examples:
    Catching a scanner error::

        from app.parser.lexer.scanner_exceptions import ScannerError

        try:
            scanner = CharacterScanner(source)
        except ScannerError as exc:
            print(f"Scanner failed: {exc.message}")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

__all__ = ["ScannerError"]


class ScannerError(Exception):
    """
    Root exception for all :class:`~app.parser.lexer.scanner.CharacterScanner`
    failures.

    Raised when the scanner receives an input that violates its preconditions,
    such as a non-string source argument.

    Attributes:
        message: Human-readable description of the failure.

    Examples:
        >>> raise ScannerError("source must be a str")
        Traceback (most recent call last):
            ...
        app.parser.lexer.scanner_exceptions.ScannerError: source must be a str
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
