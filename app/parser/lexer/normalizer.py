"""
COBOL Source Normalizer.

Purpose:
    Convert raw COBOL source text into a normalized form that downstream
    stages (Character Scanner, Lexer) can consume without needing to
    understand column-position semantics.

    The Normalizer is the third stage of the COBOL compiler pipeline,
    sitting immediately after the Format Detector.

Responsibilities:
    For FIXED format source:
        - Strip columns 1–6 (Sequence Number Area).
        - Strip columns 73–80 (Program-ID / Card-ID Area).
        - Preserve column 7 (Indicator Area) and columns 8–72 (Area A + B).
        - Preserve line order exactly.

    For FREE format source:
        - Return the source unchanged.

Non-responsibilities:
    - Continuation line handling.
    - COPY book expansion.
    - REPLACE processing.
    - EXEC SQL / EXEC CICS handling.
    - Scanning, lexing, or parsing.
    - Any COBOL semantic knowledge.

Dependencies:
    - :mod:`app.parser.lexer.source_format` — ``SourceFormat`` enum.
    - :mod:`app.parser.lexer.exceptions`    — ``NormalizationError``.
    - Python standard library only (no third-party packages).

Fixed Format Column Layout (ANSI reference format):

    Columns  1– 6:  Sequence Number Area  (removed by this stage)
    Column       7:  Indicator Area         (preserved)
    Columns  8–11:  Area A                 (preserved)
    Columns 12–72:  Area B                 (preserved)
    Columns 73–80:  Program-ID Area        (removed by this stage)

    After normalization each fixed-format line contains only the content
    that was in columns 7–72 (up to 66 characters), with its original
    line terminator restored.

Examples:
    Normalizing a fixed-format line::

        from app.parser.lexer.normalizer import SourceNormalizer
        from app.parser.lexer.source_format import SourceFormat

        normalizer = SourceNormalizer()

        source = "000100 IDENTIFICATION DIVISION.                         CBL001\\n"
        result = normalizer.normalize(source, SourceFormat.FIXED)
        # result == " IDENTIFICATION DIVISION.                        \\n"

    Normalizing free-format source (pass-through)::

        source = "IDENTIFICATION DIVISION.\\n"
        result = normalizer.normalize(source, SourceFormat.FREE)
        assert result == source

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.lexer.exceptions import NormalizationError
from app.parser.lexer.source_format import SourceFormat

__all__ = ["SourceNormalizer"]

# ---------------------------------------------------------------------------
# Fixed-format column constants (1-indexed, inclusive on both ends).
# Python slicing uses 0-indexed, exclusive-end notation, so:
#   columns  1– 6  → s[0:6]
#   columns  7–72  → s[6:72]
#   columns 73–80  → s[72:80]  (ignored)
# ---------------------------------------------------------------------------
_FIXED_SEQ_END: int = 6  # end of sequence number area (0-indexed exclusive)
_FIXED_BODY_END: int = 72  # end of Area B / start of card-id area (0-indexed exclusive)


class SourceNormalizer:
    """
    Normalize raw COBOL source text for downstream lexical analysis.

    The normalizer applies format-specific transformations to strip
    column-position artefacts that have no semantic meaning for later
    pipeline stages.  It is intentionally kept stateless so that a single
    instance can be reused safely across multiple source units.

    For FIXED format:
        Sequence numbers (columns 1–6) and the program-ID area (columns
        73–80) are stripped from every source line.  Columns 7–72 (the
        Indicator, Area A, and Area B) are preserved verbatim.  Lines
        shorter than 7 characters have their content preserved as-is
        (no padding is applied).

    For FREE format:
        The source is returned unchanged.

    Raises:
        NormalizationError:
            If *source_format* is :attr:`~SourceFormat.UNKNOWN`, or if
            *source* is not a :class:`str`.

    Examples:
        >>> normalizer = SourceNormalizer()
        >>> from app.parser.lexer.source_format import SourceFormat
        >>> normalizer.normalize("", SourceFormat.FREE)
        ''
    """

    def normalize(
        self,
        source: str,
        source_format: SourceFormat,
    ) -> str:
        """
        Return the normalized form of *source* for the given *source_format*.

        Args:
            source:
                The raw COBOL source text to normalize.  Must be a
                :class:`str`; bytes are not accepted.
            source_format:
                The detected format of the source.  Must be either
                :attr:`SourceFormat.FIXED` or :attr:`SourceFormat.FREE`.

        Returns:
            The normalized source as a :class:`str`.  For ``FREE`` format
            this is identical to *source*.  For ``FIXED`` format each line
            has its sequence number area and program-ID area removed.

        Raises:
            NormalizationError:
                - If *source* is not a :class:`str`.
                - If *source_format* is :attr:`SourceFormat.UNKNOWN`.

        Examples:
            >>> n = SourceNormalizer()
            >>> from app.parser.lexer.source_format import SourceFormat
            >>> n.normalize("hello\\n", SourceFormat.FREE)
            'hello\\n'
        """
        if not isinstance(source, str):
            raise NormalizationError(
                f"source must be a str, got {type(source).__name__!r}"
            )

        if source_format is SourceFormat.UNKNOWN:
            raise NormalizationError(
                "Cannot normalize source with SourceFormat.UNKNOWN. "
                "Run the Format Detector first."
            )

        logger.debug(
            "Normalizing source ({} format, {} chars)", source_format.value, len(source)
        )

        if source_format is SourceFormat.FREE:
            logger.debug("FREE format: returning source unchanged")
            return source

        # FIXED format path
        return self._normalize_fixed(source)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_fixed(self, source: str) -> str:
        """
        Apply fixed-format column stripping to every line in *source*.

        Each logical line in the source is processed independently:

        * Lines shorter than or equal to 6 characters consist entirely of
          the Sequence Number Area and are reduced to an empty line (only
          the line terminator is retained).
        * Lines longer than 6 characters have their first 6 columns
          removed.  If the remaining text is longer than 66 characters
          (i.e. the line extended into columns 73–80), the trailing excess
          is also removed.

        The line terminator (``\\r\\n``, ``\\n``, or ``\\r``) from the
        original line is preserved exactly.

        Args:
            source: Raw COBOL fixed-format source text.

        Returns:
            Normalized source with sequence numbers and program-ID columns
            removed.
        """
        normalized_lines: list[str] = []

        for line in _split_preserving_endings(source):
            body, ending = _split_line_ending(line)

            if len(body) <= _FIXED_SEQ_END:
                # The entire visible content falls within the sequence
                # number area; replace with an empty body.
                normalized_lines.append(ending)
            else:
                # Strip sequence number area (cols 1–6) and card-id area
                # (cols 73–80).  body[6:72] gives cols 7–72 inclusive.
                content = body[_FIXED_SEQ_END:_FIXED_BODY_END]
                normalized_lines.append(content + ending)

        return "".join(normalized_lines)


# ---------------------------------------------------------------------------
# Module-level helpers (not part of the public API)
# ---------------------------------------------------------------------------


def _split_preserving_endings(source: str) -> list[str]:
    """
    Split *source* into lines while preserving each line's terminator.

    Unlike :meth:`str.splitlines`, this function keeps ``\\r\\n``, ``\\n``,
    and ``\\r`` attached to the line they terminate, and correctly handles
    a trailing line that has no terminator.

    Args:
        source: The raw source text to split.

    Returns:
        A list of strings, each ending with its original line terminator
        (or no terminator for the final line if the source does not end
        with a newline).

    Examples:
        >>> _split_preserving_endings("abc\\ndef\\n")
        ['abc\\n', 'def\\n']
        >>> _split_preserving_endings("abc\\r\\ndef")
        ['abc\\r\\n', 'def']
    """
    lines: list[str] = []
    i = 0
    n = len(source)

    while i < n:
        # Find the next line terminator.
        cr = source.find("\r", i)
        lf = source.find("\n", i)

        if cr == -1 and lf == -1:
            # No more line terminators; remainder is the last line.
            lines.append(source[i:])
            break

        if cr != -1 and (lf == -1 or cr <= lf):
            # CR found; check for CRLF.
            if lf == cr + 1:
                end = lf + 1  # CRLF
            else:
                end = cr + 1  # bare CR
        else:
            end = lf + 1  # bare LF

        lines.append(source[i:end])
        i = end

    return lines


def _split_line_ending(line: str) -> tuple[str, str]:
    """
    Separate the visible body of *line* from its line terminator.

    Args:
        line: A single source line, possibly ending with ``\\r\\n``,
              ``\\n``, or ``\\r``.

    Returns:
        A ``(body, ending)`` tuple where *body* is the line content
        without the terminator and *ending* is the terminator string
        (empty string if *line* has no terminator).

    Examples:
        >>> _split_line_ending("hello\\r\\n")
        ('hello', '\\r\\n')
        >>> _split_line_ending("hello")
        ('hello', '')
    """
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""
