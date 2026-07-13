"""
Source Position Model.

Purpose:
    Provide an immutable, hashable value type that records the exact
    location of every token within a COBOL source file.  Accurate
    position tracking is a prerequisite for producing meaningful
    compiler diagnostics, IDE hover information, and cross-reference
    data.

Responsibilities:
    - Represent a single point in source text via line, column, and
      byte-offset coordinates.
    - Carry the originating filename so that positions remain
      self-contained and unambiguous across multi-file compilation
      units (e.g. after COPY-book expansion).
    - Remain entirely immutable after construction; no mutation is
      ever permitted.

Dependencies:
    - Python standard library only (``dataclasses``).

Examples:
    Creating a position for the first character of a file::

        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="PAYROLL.cbl")
        print(pos)
        # Position(line=1, column=1, offset=0, filename='PAYROLL.cbl')

    Positions support equality and hashing::

        p1 = Position(line=1, column=1, offset=0, filename="A.cbl")
        p2 = Position(line=1, column=1, offset=0, filename="A.cbl")
        assert p1 == p2
        assert hash(p1) == hash(p2)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Position"]


@dataclass(frozen=True, slots=True)
class Position:
    """
    Immutable source location for a single token or diagnostic point.

    A ``Position`` instance identifies exactly where in the source text
    a token begins.  All four fields are required; there are no
    optional attributes.

    Attributes:
        line:
            One-based line number within the source file.  The first
            line of any file is ``1``.
        column:
            One-based column number within the current line.  The
            first character of each line is ``1``.
        offset:
            Zero-based byte offset from the beginning of the source
            string.  Useful for slicing the raw source buffer without
            re-scanning line breaks.
        filename:
            Absolute or relative path of the source file that contains
            this position.  For synthetic tokens (e.g. inserted during
            COPY-book expansion) this may be the COPY-book member name.

    Examples:
        >>> pos = Position(line=10, column=8, offset=342, filename="WS.cbl")
        >>> pos.line
        10
        >>> pos.column
        8
        >>> pos.offset
        342
        >>> pos.filename
        'WS.cbl'
    """

    line: int
    column: int
    offset: int
    filename: str
