"""
COBOL Parser Exception Hierarchy.

Purpose:
    Define the typed exception classes used throughout the COBOL lexer
    pipeline.  Centralising exceptions here prevents circular imports and
    ensures every stage of the pipeline raises a structured, typed error
    that callers can handle precisely.

Responsibilities:
    - Provide :class:`ParserError` as the root exception for all pipeline
      errors.
    - Provide :class:`NormalizationError` for failures in the
      :class:`~app.parser.lexer.normalizer.SourceNormalizer` stage.

Non-responsibilities:
    - Scanning, lexing, or parsing logic.
    - Any COBOL semantic knowledge.

Dependencies:
    - Python standard library only.

Examples:
    Catching any parser pipeline error::

        from app.parser.lexer.exceptions import ParserError

        try:
            result = normalizer.normalize(source, fmt)
        except ParserError as exc:
            print(exc)

    Catching a normalizer-specific error::

        from app.parser.lexer.exceptions import NormalizationError

        try:
            result = normalizer.normalize(source, fmt)
        except NormalizationError as exc:
            print(f"Normalization failed: {exc.message}")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

__all__ = ["NormalizationError", "ParserError"]


class ParserError(Exception):
    """
    Root exception for all COBOL parser pipeline errors.

    All concrete pipeline exceptions inherit from this class so that
    callers can catch the entire family of parser errors with a single
    ``except ParserError`` clause, or opt into a more specific subclass.

    Attributes:
        message: Human-readable description of the failure.

    Examples:
        >>> raise ParserError("something went wrong")
        Traceback (most recent call last):
            ...
        app.parser.lexer.exceptions.ParserError: something went wrong
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NormalizationError(ParserError):
    """
    Raised when :class:`~app.parser.lexer.normalizer.SourceNormalizer`
    cannot normalise the supplied source text.

    This error is raised for inputs that violate preconditions, such as
    passing a non-string value or requesting normalisation for an
    unsupported :class:`~app.parser.lexer.source_format.SourceFormat`
    (e.g. ``SourceFormat.UNKNOWN``).

    Attributes:
        message: Human-readable description of the failure.

    Examples:
        >>> from app.parser.lexer.exceptions import NormalizationError
        >>> raise NormalizationError("unsupported format: unknown")
        Traceback (most recent call last):
            ...
        app.parser.lexer.exceptions.NormalizationError: unsupported format: unknown
    """
