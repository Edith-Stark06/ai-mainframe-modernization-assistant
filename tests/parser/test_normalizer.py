"""
Tests for the COBOL Source Normalizer.

Purpose:
    Verify that :class:`~app.parser.lexer.normalizer.SourceNormalizer`
    correctly strips fixed-format column artefacts, passes free-format
    source through unchanged, and raises structured errors for invalid
    inputs.

Responsibilities:
    - Fixed format: sequence numbers removed, identification columns removed.
    - Free format: source returned unchanged.
    - Empty source: handled without error.
    - Invalid input: non-str and SourceFormat.UNKNOWN raise NormalizationError.
    - Line order preserved.
    - Line terminators preserved (LF, CRLF, bare CR).

Dependencies:
    - :mod:`app.parser.lexer.normalizer`    — subject under test.
    - :mod:`app.parser.lexer.source_format` — SourceFormat enum.
    - :mod:`app.parser.lexer.exceptions`    — NormalizationError.
    - :mod:`pytest`                         — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.parser.lexer.exceptions import NormalizationError
from app.parser.lexer.normalizer import SourceNormalizer
from app.parser.lexer.source_format import SourceFormat

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

# A classic fixed-format COBOL program.  Each line is exactly 80 columns:
# cols 1-6   = sequence number
# col  7     = indicator (space = normal code line)
# cols 8-72  = Area A + Area B
# cols 73-80 = program-id card field
#
# Construction: seq(6) + indicator+content padded to 66 chars + card_id(8) + \n
# Total visible chars = 6 + 66 + 8 = 80.
_FIXED_LINE_1 = (
    "000100 IDENTIFICATION DIVISION.                                         CBL0001 \n"
)
_FIXED_LINE_2 = (
    "000200 PROGRAM-ID.    HELLO-WORLD.                                      CBL0001 \n"
)
_FIXED_LINE_3 = "000300 PROCEDURE DIVISION.                                               CBL0001 \n"
_FIXED_LINE_4 = "000400     DISPLAY 'HELLO, WORLD!'.                                      CBL0001 \n"
_FIXED_LINE_5 = "000500     STOP RUN.                                                     CBL0001 \n"

_FIXED_SOURCE = (
    _FIXED_LINE_1 + _FIXED_LINE_2 + _FIXED_LINE_3 + _FIXED_LINE_4 + _FIXED_LINE_5
)

# Expected normalized output: cols 7-72 (66 chars) + original line ending.
# Each body below is exactly 66 chars before the newline.
_NORM_LINE_1 = " IDENTIFICATION DIVISION.                                         \n"
_NORM_LINE_2 = " PROGRAM-ID.    HELLO-WORLD.                                      \n"
_NORM_LINE_3 = " PROCEDURE DIVISION.                                              \n"
_NORM_LINE_4 = "     DISPLAY 'HELLO, WORLD!'.                                     \n"
_NORM_LINE_5 = "     STOP RUN.                                                    \n"

_NORMALIZED_FIXED = (
    _NORM_LINE_1 + _NORM_LINE_2 + _NORM_LINE_3 + _NORM_LINE_4 + _NORM_LINE_5
)


# ---------------------------------------------------------------------------
# Fixed format
# ---------------------------------------------------------------------------


class TestFixedFormat:
    """Normalization of COBOL fixed-format source."""

    def test_returns_string(self) -> None:
        """normalize() returns a str for fixed-format input."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize(_FIXED_SOURCE, SourceFormat.FIXED)
        assert isinstance(result, str)

    def test_sequence_numbers_removed(self) -> None:
        """Columns 1–6 (sequence numbers) are stripped from every line."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize(_FIXED_SOURCE, SourceFormat.FIXED)

        for line in result.splitlines():
            # After normalization col-1 of the output was formerly col-7,
            # so no line should start with a digit (sequence number digit).
            # (Real content in col 7 is always a space or indicator char.)
            assert not line[:6].isdigit(), f"Sequence digits found in: {line!r}"

    def test_identification_columns_ignored(self) -> None:
        """Columns 73–80 (program-ID card area) are stripped."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize(_FIXED_SOURCE, SourceFormat.FIXED)

        # Our test card field is "CBL0001 "; it must not appear in the output.
        assert "CBL0001" not in result

    def test_content_preserved(self) -> None:
        """Area A and Area B content (cols 7–72) is preserved exactly."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize(_FIXED_SOURCE, SourceFormat.FIXED)
        assert result == _NORMALIZED_FIXED

    def test_line_order_preserved(self) -> None:
        """The order of lines in the output matches the input."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize(_FIXED_SOURCE, SourceFormat.FIXED)
        result_lines = result.splitlines()

        assert "IDENTIFICATION DIVISION." in result_lines[0]
        assert "PROGRAM-ID." in result_lines[1]
        assert "PROCEDURE DIVISION." in result_lines[2]
        assert "DISPLAY" in result_lines[3]
        assert "STOP RUN." in result_lines[4]

    def test_short_lines_handled(self) -> None:
        """Lines shorter than 7 characters do not raise an error."""
        normalizer = SourceNormalizer()
        source = "000100\n"  # exactly 6 visible chars — pure sequence number
        result = normalizer.normalize(source, SourceFormat.FIXED)
        # The body (all 6 chars) is the sequence area; normalized body is empty.
        assert result == "\n"

    def test_very_short_line(self) -> None:
        """Lines shorter than 6 characters are handled without error."""
        normalizer = SourceNormalizer()
        source = "001\n"  # only 3 chars
        result = normalizer.normalize(source, SourceFormat.FIXED)
        # Entire body falls within sequence area → empty normalized body.
        assert result == "\n"

    def test_crlf_line_endings_preserved(self) -> None:
        """CRLF line endings are preserved after normalization."""
        line = "000100 IDENTIFICATION DIVISION.                         CBL0001 \r\n"
        normalizer = SourceNormalizer()
        result = normalizer.normalize(line, SourceFormat.FIXED)
        assert result.endswith("\r\n")

    def test_bare_cr_line_endings_preserved(self) -> None:
        """Bare CR line endings are preserved after normalization."""
        line = "000100 IDENTIFICATION DIVISION.                         CBL0001 \r"
        normalizer = SourceNormalizer()
        result = normalizer.normalize(line, SourceFormat.FIXED)
        assert result.endswith("\r")

    def test_no_trailing_newline_preserved(self) -> None:
        """A line with no trailing newline is handled correctly."""
        line = "000100 IDENTIFICATION DIVISION.                         CBL0001 "
        normalizer = SourceNormalizer()
        result = normalizer.normalize(line, SourceFormat.FIXED)
        assert not result.endswith("\n")
        assert "IDENTIFICATION DIVISION." in result

    def test_comment_indicator_preserved(self) -> None:
        """Column 7 indicator character (e.g. '*' for comment) is preserved."""
        # col 7 = '*' → comment line; this must survive normalization.
        line = "000100*  THIS IS A COMMENT LINE.                         CBL0001 \n"
        normalizer = SourceNormalizer()
        result = normalizer.normalize(line, SourceFormat.FIXED)
        assert result.startswith("*")

    def test_multiline_fixed_source(self) -> None:
        """Multiple lines are all normalized independently."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize(_FIXED_SOURCE, SourceFormat.FIXED)
        assert len(result.splitlines()) == len(_FIXED_SOURCE.splitlines())

    def test_line_wider_than_80_columns(self) -> None:
        """Lines longer than 80 columns are truncated at column 72."""
        line = "000100 IDENTIFICATION DIVISION.                         CBL0001EXTRA_GARBAGE\n"
        normalizer = SourceNormalizer()
        result = normalizer.normalize(line, SourceFormat.FIXED)
        # cols 7-72 = 66 chars; cols 73+ are dropped.
        body = result.rstrip("\n")
        assert len(body) == 66
        assert "EXTRA_GARBAGE" not in result


# ---------------------------------------------------------------------------
# Free format
# ---------------------------------------------------------------------------


class TestFreeFormat:
    """Normalization of COBOL free-format source."""

    def test_returns_source_unchanged(self) -> None:
        """normalize() returns the source unchanged for FREE format."""
        source = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. HELLO-WORLD.\n"
            "PROCEDURE DIVISION.\n"
            "    DISPLAY 'HELLO'.\n"
            "    STOP RUN.\n"
        )
        normalizer = SourceNormalizer()
        result = normalizer.normalize(source, SourceFormat.FREE)
        assert result == source

    def test_free_format_with_inline_comment(self) -> None:
        """FREE format source containing *> comments is returned unchanged."""
        source = "MOVE A TO B. *> inline comment\n"
        normalizer = SourceNormalizer()
        result = normalizer.normalize(source, SourceFormat.FREE)
        assert result == source

    def test_free_format_returns_string(self) -> None:
        """normalize() returns a str for free-format input."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize("STOP RUN.\n", SourceFormat.FREE)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Empty source
# ---------------------------------------------------------------------------


class TestEmptySource:
    """Normalization of empty source strings."""

    def test_empty_fixed(self) -> None:
        """normalize() returns empty string for empty fixed-format source."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize("", SourceFormat.FIXED)
        assert result == ""

    def test_empty_free(self) -> None:
        """normalize() returns empty string for empty free-format source."""
        normalizer = SourceNormalizer()
        result = normalizer.normalize("", SourceFormat.FREE)
        assert result == ""


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


class TestInvalidInput:
    """Behaviour for invalid or unsupported inputs."""

    def test_unknown_format_raises(self) -> None:
        """normalize() raises NormalizationError for SourceFormat.UNKNOWN."""
        normalizer = SourceNormalizer()
        with pytest.raises(NormalizationError):
            normalizer.normalize("IDENTIFICATION DIVISION.\n", SourceFormat.UNKNOWN)

    def test_unknown_format_error_message(self) -> None:
        """NormalizationError for UNKNOWN format carries a meaningful message."""
        normalizer = SourceNormalizer()
        with pytest.raises(NormalizationError) as exc_info:
            normalizer.normalize("", SourceFormat.UNKNOWN)
        assert exc_info.value.message

    def test_non_string_source_raises(self) -> None:
        """normalize() raises NormalizationError when source is not a str."""
        normalizer = SourceNormalizer()
        with pytest.raises(NormalizationError):
            normalizer.normalize(b"IDENTIFICATION DIVISION.\n", SourceFormat.FIXED)  # type: ignore[arg-type]

    def test_none_source_raises(self) -> None:
        """normalize() raises NormalizationError when source is None."""
        normalizer = SourceNormalizer()
        with pytest.raises(NormalizationError):
            normalizer.normalize(None, SourceFormat.FIXED)  # type: ignore[arg-type]

    def test_normalization_error_is_parser_error(self) -> None:
        """NormalizationError is a subclass of ParserError."""
        from app.parser.lexer.exceptions import ParserError

        normalizer = SourceNormalizer()
        with pytest.raises(NormalizationError) as exc_info:
            normalizer.normalize("", SourceFormat.UNKNOWN)
        assert isinstance(exc_info.value, ParserError)

    def test_normalization_error_attributes(self) -> None:
        """NormalizationError carries .message and str() representation."""
        err = NormalizationError("test error")
        assert err.message == "test error"
        assert "test error" in str(err)
