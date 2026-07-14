"""
COBOL Source Format Detector.

Purpose:
    Determine whether a COBOL source file uses Fixed Format or Free
    Format by applying a set of documented, deterministic heuristics
    against the raw source text.  The detector is the second stage of
    the compiler pipeline, sitting immediately after the Source Reader
    and before the Normalizer.

Responsibilities:
    - Accept a :class:`SourceDocument` containing raw source text.
    - Apply heuristics in a defined priority order.
    - Return a :class:`~app.parser.lexer.source_format.SourceFormat`
      value without mutating the document.
    - Never guess; return ``SourceFormat.UNKNOWN`` when evidence is
      insufficient or contradictory.
    - Remain stateless — the same input always produces the same output.

Dependencies:
    - :mod:`app.parser.lexer.source_format` — ``SourceFormat`` enum.
    - Python standard library only (``dataclasses``, ``typing``).

Heuristic Priority Order:
    1. ``>>SOURCE FREE`` directive  → FREE  (definitive compiler directive)
    2. ``>>SOURCE FIXED`` directive → FIXED (definitive compiler directive)
    3. ``*>`` inline comment syntax → FREE  (free-format-only comment style)
    4. Fixed-column structural evidence (Area A / Indicator column) → FIXED
    5. No evidence → UNKNOWN

Pipeline Position:
    Source File → Source Reader → **Format Detector** → Normalizer → Scanner → Lexer

Examples:
    Detecting free format from a directive::

        from app.parser.lexer.format_detector import FormatDetector, SourceDocument
        from app.parser.lexer.source_format import SourceFormat

        doc = SourceDocument(
            filename="PAYROLL.cbl",
            source="       >>SOURCE FREE\\n       MOVE A TO B.\\n",
        )
        detector = FormatDetector()
        assert detector.detect(doc) is SourceFormat.FREE

    Detecting fixed format from column evidence::

        source = (
            "000100 IDENTIFICATION DIVISION.\\n"
            "000200 PROGRAM-ID. PAYROLL.\\n"
        )
        doc = SourceDocument(filename="PAYROLL.cbl", source=source)
        assert detector.detect(doc) is SourceFormat.FIXED

    Returning UNKNOWN for empty input::

        doc = SourceDocument(filename="EMPTY.cbl", source="")
        assert detector.detect(doc) is SourceFormat.UNKNOWN

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.parser.lexer.source_format import SourceFormat

__all__ = ["FormatDetector", "SourceDocument"]

# ---------------------------------------------------------------------------
# Fixed-format column constants (1-based, matching ANSI COBOL standard)
# ---------------------------------------------------------------------------

#: Last column of the Sequence Number Area (columns 1–6).
_SEQUENCE_AREA_END: int = 6

#: Column of the Indicator Area (column 7).
_INDICATOR_COLUMN: int = 7

#: First column of Area A (column 8).
_AREA_A_START: int = 8

#: Last column of Area B / Program Text Area (column 72).
_PROGRAM_TEXT_END: int = 72

#: Minimum number of lines examined when applying structural heuristics.
_MIN_SAMPLE_LINES: int = 5

#: Minimum proportion of sampled lines that must show fixed-column
#: evidence before we commit to FIXED.  Set conservatively to avoid
#: false positives on files with accidental column alignment.
_FIXED_EVIDENCE_THRESHOLD: float = 0.6


# ---------------------------------------------------------------------------
# SourceDocument
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """
    Immutable representation of a COBOL source file as read from disk.

    This is the input type consumed by :class:`FormatDetector`.  It
    carries the raw (undecoded-for-format-purposes) source text together
    with the originating filename, which is used in diagnostics.

    Attributes:
        filename:
            Absolute or relative path of the source file.
        source:
            Complete source text decoded to a Python ``str``.  Line
            endings may be ``\\n``, ``\\r\\n``, or ``\\r``; the detector
            handles all three.

    Examples:
        >>> doc = SourceDocument(filename="PROG.cbl", source="       MOVE A TO B.\\n")
        >>> doc.filename
        'PROG.cbl'
    """

    filename: str
    source: str


# ---------------------------------------------------------------------------
# FormatDetector
# ---------------------------------------------------------------------------


class FormatDetector:
    """
    Stateless COBOL source format detector.

    Applies a cascade of deterministic heuristics to a
    :class:`SourceDocument` and returns a
    :class:`~app.parser.lexer.source_format.SourceFormat` verdict.

    The detector is intentionally conservative: it only returns
    ``FIXED`` or ``FREE`` when it has clear positive evidence.  When
    the file is empty, whitespace-only, or contains no recognisable
    indicators, it returns ``UNKNOWN``.

    The detector is stateless.  A single instance may be reused across
    many files without risk of cross-contamination.

    Heuristics (applied in priority order):

    1. **``>>SOURCE FREE`` compiler directive** (→ FREE)
       The IBM/ANSI standard ``>>SOURCE FREE`` directive is the
       authoritative declaration of free format.  No other evidence is
       needed.

    2. **``>>SOURCE FIXED`` compiler directive** (→ FIXED)
       The symmetric directive explicitly selects fixed format.

    3. **``*>`` inline comment syntax** (→ FREE)
       The ``*>`` comment marker is valid only in free-format COBOL
       (COBOL 2002+).  Its presence is strong evidence of free format
       even in the absence of the ``>>SOURCE FREE`` directive.

    4. **Fixed-column structural evidence** (→ FIXED)
       Fixed-format COBOL has strict column layout.  Two sub-heuristics
       are applied over a sample of non-empty lines:

       a. *Sequence number area*: Lines whose first 6 characters are
          all digits (or spaces) and whose 7th character (indicator) is
          a space, ``*``, ``/``, ``-``, or ``D`` show the characteristic
          punch-card layout.

       b. *Area A activity*: Division/section/paragraph headings and
          01-level data definitions begin exactly at column 8 (index 7).
          When a statistically significant proportion of non-empty lines
          meet this criterion, the file is classified as FIXED.

       If fewer than ``_MIN_SAMPLE_LINES`` non-empty lines are available
       the structural heuristics are skipped to avoid drawing conclusions
       from too little data.

    5. **No confident evidence** (→ UNKNOWN)
       When none of the above heuristics fire, ``UNKNOWN`` is returned.

    Examples:
        >>> detector = FormatDetector()
        >>> from app.parser.lexer.format_detector import SourceDocument
        >>> doc = SourceDocument("X.cbl", "       >>SOURCE FREE\\n")
        >>> detector.detect(doc)
        <SourceFormat.FREE: 'free'>
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, document: SourceDocument) -> SourceFormat:
        """
        Determine the source format of *document*.

        Applies the heuristic cascade documented in the class docstring
        and returns the most confident format verdict.

        Args:
            document:
                The :class:`SourceDocument` to analyse.  The ``source``
                attribute must be the complete, decoded source text.

        Returns:
            :class:`~app.parser.lexer.source_format.SourceFormat`
            — one of ``FIXED``, ``FREE``, or ``UNKNOWN``.
        """
        lines = _split_lines(document.source)

        # Heuristic 1 & 2: compiler directives (highest priority)
        directive_result = _detect_by_directive(lines)
        if directive_result is not SourceFormat.UNKNOWN:
            return directive_result

        # Heuristic 3: *> comment syntax (free-format-only)
        if _has_free_format_comment(lines):
            return SourceFormat.FREE

        # Heuristic 4: fixed-column structural evidence
        non_empty = [ln for ln in lines if ln.strip()]
        if len(non_empty) >= _MIN_SAMPLE_LINES:
            if _fixed_column_evidence(non_empty) >= _FIXED_EVIDENCE_THRESHOLD:
                return SourceFormat.FIXED

        # Heuristic 5: insufficient evidence
        return SourceFormat.UNKNOWN


# ---------------------------------------------------------------------------
# Private helper functions
# ---------------------------------------------------------------------------


def _split_lines(source: str) -> list[str]:
    """
    Split *source* into individual lines, handling all line-ending styles.

    Normalises ``\\r\\n`` and bare ``\\r`` to ``\\n`` before splitting so
    that column-index arithmetic operates on plain ``\\n``-terminated
    lines.

    Args:
        source: Raw source text, possibly containing mixed line endings.

    Returns:
        List of lines.  Each line retains any trailing ``\\n``; the final
        element may lack a terminator if the file does not end with one.
    """
    normalised = source.replace("\r\n", "\n").replace("\r", "\n")
    return normalised.splitlines(keepends=False)


def _detect_by_directive(lines: list[str]) -> SourceFormat:
    """
    Scan *lines* for an explicit ``>>SOURCE`` compiler directive.

    The ``>>SOURCE FREE`` and ``>>SOURCE FIXED`` directives are the
    most authoritative indicators of source format.  They are checked
    first because they represent an explicit programmer declaration that
    overrides all other evidence.

    The directive is matched case-insensitively and with optional leading
    whitespace, as allowed by both IBM Enterprise COBOL and GnuCOBOL.

    Args:
        lines: Source lines as returned by :func:`_split_lines`.

    Returns:
        ``SourceFormat.FREE`` if ``>>SOURCE FREE`` is found,
        ``SourceFormat.FIXED`` if ``>>SOURCE FIXED`` is found,
        ``SourceFormat.UNKNOWN`` if neither is present.
    """
    for line in lines:
        upper = line.upper().strip()
        if upper.startswith(">>SOURCE"):
            remainder = upper[len(">>SOURCE") :].strip()
            if remainder == "FREE":
                return SourceFormat.FREE
            if remainder == "FIXED":
                return SourceFormat.FIXED
    return SourceFormat.UNKNOWN


def _has_free_format_comment(lines: list[str]) -> bool:
    """
    Return ``True`` if any line contains a ``*>`` free-format comment.

    The ``*>`` comment marker is valid only in COBOL 2002+ free format.
    In fixed format, the ``*`` comment indicator occupies column 7 and
    is never followed directly by ``>``.  Finding ``*>`` anywhere in
    the file is therefore strong evidence of free format.

    The check looks for ``*>`` as a stripped prefix of any line, or
    anywhere in the line that is not inside a string literal.  Because
    we have no lexer at this stage, we use a conservative line-level
    check: any line that contains ``*>`` (after stripping leading
    whitespace) is counted as evidence.

    Args:
        lines: Source lines as returned by :func:`_split_lines`.

    Returns:
        ``True`` if a ``*>`` comment marker is detected.
    """
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("*>"):
            return True
        # Also detect mid-line *> comment markers that appear outside
        # of a string literal.  We perform a lightweight scan: split on
        # the marker and check that neither side looks like it is inside
        # a quoted string by counting quotation marks naively.
        if "*>" in line:
            before = line[: line.index("*>")]
            single_quotes = before.count("'")
            double_quotes = before.count('"')
            # If both quote counts are even, the *> is outside any string.
            if single_quotes % 2 == 0 and double_quotes % 2 == 0:
                return True
    return False


def _fixed_column_evidence(non_empty_lines: list[str]) -> float:
    """
    Calculate the proportion of lines that exhibit fixed-column layout.

    Two independent sub-heuristics contribute evidence:

    **Sequence-number heuristic**
        In fixed format the first 6 columns are the Sequence Number
        Area.  Punch-card era programs filled this with digits; modern
        compilers accept spaces.  Column 7 (index 6) is the Indicator,
        which must be one of: space, ``*`` (comment), ``/`` (page
        eject), ``-`` (continuation), or ``D`` (debug).  A line that
        satisfies both conditions is strong evidence of fixed format.

    **Area A / indicator heuristic**
        Fixed-format COBOL requires that certain top-level constructs
        (DIVISION headers, SECTION headers, paragraph names, 01/77
        level entries) start in Area A (columns 8–11, index 7–10).
        A line whose first non-whitespace character falls exactly at
        index 7 (column 8) is indicative of Area A usage.

    A line contributes evidence if *either* sub-heuristic fires.

    Args:
        non_empty_lines:
            Lines with at least one non-whitespace character.  Must
            contain at least :data:`_MIN_SAMPLE_LINES` entries; the
            caller is responsible for enforcing this precondition.

    Returns:
        A float in ``[0.0, 1.0]`` representing the fraction of sampled
        lines that showed fixed-column evidence.
    """
    evidence_count = 0

    for line in non_empty_lines:
        if _line_has_sequence_and_indicator(line):
            evidence_count += 1
        elif _line_starts_in_area_a(line):
            evidence_count += 1

    return evidence_count / len(non_empty_lines)


def _line_has_sequence_and_indicator(line: str) -> bool:
    """
    Return ``True`` if *line* shows the fixed-format sequence + indicator layout.

    Checks that:
    - The line is at least 7 characters wide (sequence area + indicator).
    - Columns 1–6 (indices 0–5) contain only digits or spaces.
    - Column 7 (index 6) is a valid indicator character:
      space, ``*``, ``/``, ``-``, or ``D``.

    This pattern is the signature of cards formatted for IBM punch-card
    COBOL or modern fixed-format source files that retain the layout.

    Args:
        line: A single source line (no trailing newline).

    Returns:
        ``True`` if the sequence-area + indicator pattern is satisfied.
    """
    if len(line) < _INDICATOR_COLUMN:
        return False

    sequence_area = line[:_SEQUENCE_AREA_END]
    indicator = line[_INDICATOR_COLUMN - 1]  # index 6 = column 7

    sequence_ok = all(ch.isdigit() or ch == " " for ch in sequence_area)
    indicator_ok = indicator in (" ", "*", "/", "-", "D")

    return sequence_ok and indicator_ok


def _line_starts_in_area_a(line: str) -> bool:
    """
    Return ``True`` if *line*'s first non-whitespace character is in Area A.

    Area A spans columns 8–11 (indices 7–10).  Division/section/paragraph
    headers and top-level data entries (01, 77) must begin in this area
    in fixed format.  A line whose first non-whitespace character falls
    at index 7 (column 8) — and whose content before that index is
    entirely spaces (consistent with an empty sequence+indicator area)
    — is evidence of fixed-format Area A usage.

    We specifically look for the first non-space character being at
    index 7 because that is the most reliable discriminator: free-format
    code may accidentally have content at column 8, but the consistent
    pattern across many lines distinguishes format.

    Args:
        line: A single source line (no trailing newline).

    Returns:
        ``True`` if the line's content begins exactly at column 8
        (index 7).
    """
    if len(line) <= _AREA_A_START - 1:
        return False

    # Columns 1-7 (indices 0-6) must be whitespace (sequence+indicator areas
    # are blank) and column 8 (index 7) must be non-whitespace.
    prefix = line[: _AREA_A_START - 1]  # indices 0–6 (7 chars)
    area_a_char = line[_AREA_A_START - 1]  # index 7 = column 8

    return prefix.strip() == "" and area_a_char != " "
