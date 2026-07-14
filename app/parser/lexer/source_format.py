"""
COBOL Source Format Enumeration.

Purpose:
    Define the closed set of COBOL source format categories that the
    Format Detector can identify.  Source format governs how column
    positions are interpreted during tokenisation: fixed-format COBOL
    has strict column semantics, while free-format COBOL treats source
    text without positional constraints.

Responsibilities:
    - Provide a stable, serialisable enumeration of the three possible
      format outcomes: ``FIXED``, ``FREE``, and ``UNKNOWN``.
    - Serve as the return type of
      :class:`~app.parser.lexer.format_detector.FormatDetector`.
    - Remain independent of all detection logic; this module contains
      no heuristics.

Dependencies:
    - Python standard library only (``enum``).

Background:
    COBOL Fixed Format (ANSI standard reference format):

    - Columns  1– 6: Sequence Number Area (optional; ignored by most
      compilers, used for line numbering on punch cards).
    - Column      7: Indicator Area.  A ``*`` means comment; ``/``
      means page eject; ``-`` continues a non-numeric literal from the
      previous line; ``D`` is debug line.
    - Columns  8–11: Area A.  Divisions, sections, paragraph names,
      level indicators 01 and 77, and FD/SD entries must start here.
    - Columns 12–72: Area B.  All other COBOL statements start here.
    - Columns 73–80: Program-ID Area (historically the card identifier;
      ignored by modern compilers).

    COBOL Free Format (introduced in COBOL 2002):

    - No column restrictions.
    - ``>>SOURCE FREE`` compiler directive activates free format.
    - ``*>`` introduces an in-line or full-line comment.
    - Statements may begin anywhere on a line.

Examples:
    Checking whether a detected format is fixed::

        from app.parser.lexer.source_format import SourceFormat

        fmt = SourceFormat.FIXED
        if fmt is SourceFormat.FIXED:
            print("Apply fixed-column rules")

    Serialising to a string value::

        print(SourceFormat.FREE.value)   # "free"
        print(SourceFormat.UNKNOWN.value)  # "unknown"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from enum import Enum, unique

__all__ = ["SourceFormat"]


@unique
class SourceFormat(Enum):
    """
    Enumeration of the COBOL source format categories.

    The Format Detector returns one of these three members.  Downstream
    stages (Normalizer, Scanner, Lexer) consult this value to decide
    how to interpret column positions and comment syntax.

    Members:
        UNKNOWN:
            The detector could not make a confident determination.
            Callers should treat the file conservatively (e.g. refuse
            to proceed or surface a diagnostic to the user).  This is
            the safe default when evidence is ambiguous or absent.
        FIXED:
            The source file follows the ANSI COBOL reference format
            (punch-card layout).  Columns 1–6 are the sequence number
            area, column 7 is the indicator, columns 8–11 are Area A,
            and columns 12–72 are Area B.
        FREE:
            The source file uses COBOL 2002+ free format.  There are
            no fixed column constraints; statements may begin anywhere
            on a line; ``*>`` introduces a comment.

    Examples:
        >>> SourceFormat.FIXED.value
        'fixed'
        >>> SourceFormat.FREE.value
        'free'
        >>> SourceFormat.UNKNOWN.value
        'unknown'
        >>> SourceFormat["FIXED"] is SourceFormat.FIXED
        True
    """

    UNKNOWN = "unknown"
    FIXED = "fixed"
    FREE = "free"
