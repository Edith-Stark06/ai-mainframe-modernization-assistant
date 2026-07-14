"""
Unit tests for :class:`app.parser.lexer.format_detector.FormatDetector`.

Purpose:
    Verify that ``FormatDetector`` correctly classifies COBOL source
    files as FIXED, FREE, or UNKNOWN using its documented heuristic
    cascade.  Tests are grouped by heuristic so that failures pinpoint
    exactly which detection strategy broke.

Responsibilities:
    - Cover the ``>>SOURCE FREE`` / ``>>SOURCE FIXED`` directive heuristic.
    - Cover the ``*>`` free-format comment heuristic.
    - Cover the fixed-column structural evidence heuristic.
    - Cover edge cases: empty source, whitespace-only, short files,
      mixed evidence, and ambiguous content.
    - Verify determinism: the same input always produces the same result.

Dependencies:
    - :mod:`app.parser.lexer.format_detector` — ``FormatDetector``,
      ``SourceDocument`` under test.
    - :mod:`app.parser.lexer.source_format` — ``SourceFormat``.
    - pytest

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest

from app.parser.lexer.format_detector import FormatDetector, SourceDocument
from app.parser.lexer.source_format import SourceFormat

# ---------------------------------------------------------------------------
# Fixed-format source samples
# ---------------------------------------------------------------------------

# Classic punch-card layout with sequence numbers and indicator column.
_FIXED_WITH_SEQUENCE = """\
000100 IDENTIFICATION DIVISION.
000200 PROGRAM-ID. PAYROLL.
000300 ENVIRONMENT DIVISION.
000400 DATA DIVISION.
000500 WORKING-STORAGE SECTION.
000600 01  WS-AMOUNT  PIC 9(7)V99.
000700 PROCEDURE DIVISION.
000800     STOP RUN.
"""

# Modern fixed format without sequence numbers (spaces in cols 1-6).
_FIXED_NO_SEQUENCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BILLING.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-COUNTER PIC 9(4).
       PROCEDURE DIVISION.
           STOP RUN.
"""

# Fixed format with comment lines (indicator * in column 7).
_FIXED_WITH_COMMENTS = """\
000100 IDENTIFICATION DIVISION.
000200*This is a fixed-format comment.
000300 PROGRAM-ID. REPORT.
000400 ENVIRONMENT DIVISION.
000500 DATA DIVISION.
000600 WORKING-STORAGE SECTION.
000700 01  WS-LINE     PIC X(80).
000800 PROCEDURE DIVISION.
000900     STOP RUN.
"""

# ---------------------------------------------------------------------------
# Free-format source samples
# ---------------------------------------------------------------------------

_FREE_WITH_DIRECTIVE = """\
       >>SOURCE FREE
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MODERN.
       PROCEDURE DIVISION.
           STOP RUN.
"""

_FREE_WITH_FIXED_DIRECTIVE = """\
       >>SOURCE FIXED
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LEGACY.
       PROCEDURE DIVISION.
           STOP RUN.
"""

_FREE_WITH_STAR_COMMENT = """\
*> This is a free-format comment
IDENTIFICATION DIVISION.
PROGRAM-ID. NEWSTYLE.
PROCEDURE DIVISION.
    STOP RUN.
"""

_FREE_INLINE_STAR_COMMENT = """\
IDENTIFICATION DIVISION.
PROGRAM-ID. NEWSTYLE.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 WS-NAME PIC X(20). *> Name field
PROCEDURE DIVISION.
    MOVE "HELLO" TO WS-NAME.
    STOP RUN.
"""

_FREE_DIRECTIVE_LOWERCASE = """\
       >>source free
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROG1.
       PROCEDURE DIVISION.
           STOP RUN.
"""

# ---------------------------------------------------------------------------
# Ambiguous / UNKNOWN source samples
# ---------------------------------------------------------------------------

_EMPTY = ""

_WHITESPACE_ONLY = "   \n\t\n   \n"

_TOO_SHORT_TO_DECIDE = """\
       MOVE A TO B.
       STOP RUN.
"""

_AMBIGUOUS_NO_ALIGNMENT = """\
MOVE A TO B.
MOVE C TO D.
ADD 1 TO E.
COMPUTE F = G + H.
STOP RUN.
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def detector() -> FormatDetector:
    """Return a fresh :class:`FormatDetector` instance for each test."""
    return FormatDetector()


def _doc(source: str, filename: str = "TEST.cbl") -> SourceDocument:
    """Convenience helper to create a :class:`SourceDocument`."""
    return SourceDocument(filename=filename, source=source)


# ---------------------------------------------------------------------------
# SourceDocument construction
# ---------------------------------------------------------------------------


class TestSourceDocumentConstruction:
    """Tests for the :class:`SourceDocument` value type."""

    def test_filename_field(self) -> None:
        """The ``filename`` field stores the provided value."""
        doc = SourceDocument(filename="PROG.cbl", source="")
        assert doc.filename == "PROG.cbl"

    def test_source_field(self) -> None:
        """The ``source`` field stores the provided text."""
        doc = SourceDocument(filename="PROG.cbl", source="MOVE A TO B.")
        assert doc.source == "MOVE A TO B."

    def test_immutable(self) -> None:
        """``SourceDocument`` is immutable (frozen dataclass)."""
        import dataclasses

        doc = SourceDocument(filename="X.cbl", source="")
        with pytest.raises(dataclasses.FrozenInstanceError):
            doc.filename = "Y.cbl"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Heuristic 1 & 2: >>SOURCE directive
# ---------------------------------------------------------------------------


class TestDirectiveDetection:
    """Tests for the ``>>SOURCE FREE`` and ``>>SOURCE FIXED`` directives."""

    def test_source_free_directive(self, detector: FormatDetector) -> None:
        """``>>SOURCE FREE`` is detected as FREE."""
        assert detector.detect(_doc(_FREE_WITH_DIRECTIVE)) is SourceFormat.FREE

    def test_source_fixed_directive(self, detector: FormatDetector) -> None:
        """``>>SOURCE FIXED`` is detected as FIXED."""
        assert detector.detect(_doc(_FREE_WITH_FIXED_DIRECTIVE)) is SourceFormat.FIXED

    def test_directive_case_insensitive(self, detector: FormatDetector) -> None:
        """Directive matching is case-insensitive (``>>source free``)."""
        assert detector.detect(_doc(_FREE_DIRECTIVE_LOWERCASE)) is SourceFormat.FREE

    def test_directive_with_leading_spaces(self, detector: FormatDetector) -> None:
        """Directive may have leading whitespace and still be detected."""
        source = "   >>SOURCE FREE\nMOVE A TO B.\n"
        assert detector.detect(_doc(source)) is SourceFormat.FREE

    def test_directive_priority_over_other_indicators(
        self, detector: FormatDetector
    ) -> None:
        """The directive takes precedence even when other indicators disagree."""
        # >>SOURCE FREE present, but the rest looks like fixed format.
        source = (
            "       >>SOURCE FREE\n"
            "000100 IDENTIFICATION DIVISION.\n"
            "000200 PROGRAM-ID. MIXED.\n"
        )
        assert detector.detect(_doc(source)) is SourceFormat.FREE


# ---------------------------------------------------------------------------
# Heuristic 3: *> comment syntax
# ---------------------------------------------------------------------------


class TestFreeFormatCommentDetection:
    """Tests for the ``*>`` free-format comment heuristic."""

    def test_full_line_star_comment(self, detector: FormatDetector) -> None:
        """A line starting with ``*>`` is detected as FREE."""
        assert detector.detect(_doc(_FREE_WITH_STAR_COMMENT)) is SourceFormat.FREE

    def test_inline_star_comment(self, detector: FormatDetector) -> None:
        """An inline ``*>`` comment marker is detected as FREE."""
        assert detector.detect(_doc(_FREE_INLINE_STAR_COMMENT)) is SourceFormat.FREE

    def test_star_comment_with_leading_spaces(self, detector: FormatDetector) -> None:
        """``*>`` with leading spaces is still a free-format comment."""
        source = "    *> This is a comment\nMOVE A TO B.\n"
        assert detector.detect(_doc(source)) is SourceFormat.FREE


# ---------------------------------------------------------------------------
# Heuristic 4: fixed-column structural evidence
# ---------------------------------------------------------------------------


class TestFixedColumnDetection:
    """Tests for the fixed-column structural evidence heuristic."""

    def test_fixed_with_sequence_numbers(self, detector: FormatDetector) -> None:
        """Files with sequence numbers in cols 1-6 and content in Area A."""
        assert detector.detect(_doc(_FIXED_WITH_SEQUENCE)) is SourceFormat.FIXED

    def test_fixed_without_sequence_numbers(self, detector: FormatDetector) -> None:
        """Modern fixed-format files (spaces in cols 1-6) are detected."""
        assert detector.detect(_doc(_FIXED_NO_SEQUENCE)) is SourceFormat.FIXED

    def test_fixed_with_comment_lines(self, detector: FormatDetector) -> None:
        """Fixed-format files with ``*`` comment lines are detected correctly."""
        assert detector.detect(_doc(_FIXED_WITH_COMMENTS)) is SourceFormat.FIXED


# ---------------------------------------------------------------------------
# Edge cases: UNKNOWN
# ---------------------------------------------------------------------------


class TestUnknownDetection:
    """Tests that UNKNOWN is returned when evidence is insufficient."""

    def test_empty_source(self, detector: FormatDetector) -> None:
        """An empty file returns UNKNOWN."""
        assert detector.detect(_doc(_EMPTY)) is SourceFormat.UNKNOWN

    def test_whitespace_only(self, detector: FormatDetector) -> None:
        """A file containing only whitespace returns UNKNOWN."""
        assert detector.detect(_doc(_WHITESPACE_ONLY)) is SourceFormat.UNKNOWN

    def test_too_few_lines_for_structural_heuristic(
        self, detector: FormatDetector
    ) -> None:
        """Files shorter than the minimum sample size return UNKNOWN."""
        assert detector.detect(_doc(_TOO_SHORT_TO_DECIDE)) is SourceFormat.UNKNOWN

    def test_no_fixed_alignment_returns_unknown(self, detector: FormatDetector) -> None:
        """Content with no column alignment returns UNKNOWN."""
        assert detector.detect(_doc(_AMBIGUOUS_NO_ALIGNMENT)) is SourceFormat.UNKNOWN


# ---------------------------------------------------------------------------
# Line-ending handling
# ---------------------------------------------------------------------------


class TestLineEndingHandling:
    """Tests that all line-ending styles are handled correctly."""

    def test_crlf_line_endings(self, detector: FormatDetector) -> None:
        """Files with CRLF line endings are handled correctly."""
        source = _FREE_WITH_DIRECTIVE.replace("\n", "\r\n")
        assert detector.detect(_doc(source)) is SourceFormat.FREE

    def test_cr_line_endings(self, detector: FormatDetector) -> None:
        """Files with bare CR line endings are handled correctly."""
        source = _FREE_WITH_DIRECTIVE.replace("\n", "\r")
        assert detector.detect(_doc(source)) is SourceFormat.FREE

    def test_mixed_line_endings_fixed(self, detector: FormatDetector) -> None:
        """Mixed line endings do not break fixed-format detection."""
        # Replace some \n with \r\n in the fixed sample.
        lines = _FIXED_WITH_SEQUENCE.split("\n")
        source = "\r\n".join(lines[:4]) + "\n" + "\n".join(lines[4:])
        assert detector.detect(_doc(source)) is SourceFormat.FIXED


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Tests that the detector always returns the same result for the same input."""

    @pytest.mark.parametrize(
        "source, expected",
        [
            (_FREE_WITH_DIRECTIVE, SourceFormat.FREE),
            (_FREE_WITH_FIXED_DIRECTIVE, SourceFormat.FIXED),
            (_FIXED_WITH_SEQUENCE, SourceFormat.FIXED),
            (_FREE_WITH_STAR_COMMENT, SourceFormat.FREE),
            (_EMPTY, SourceFormat.UNKNOWN),
        ],
    )
    def test_repeated_calls_are_consistent(
        self, detector: FormatDetector, source: str, expected: SourceFormat
    ) -> None:
        """Calling ``detect`` twice on the same document returns the same value."""
        doc = _doc(source)
        first = detector.detect(doc)
        second = detector.detect(doc)
        assert first is second is expected

    def test_new_instance_same_result(self) -> None:
        """Two separate FormatDetector instances produce identical results."""
        doc = _doc(_FIXED_WITH_SEQUENCE)
        d1 = FormatDetector()
        d2 = FormatDetector()
        assert d1.detect(doc) is d2.detect(doc)
