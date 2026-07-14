"""
Tests for the COBOL Character Scanner.

Purpose:
    Verify that :class:`~app.parser.lexer.scanner.CharacterScanner`
    correctly iterates over source text, tracks position, handles
    newlines, supports lookahead, detects EOF, and raises typed errors
    for invalid inputs.

Responsibilities:
    - Empty source.
    - Single character.
    - Multiple characters.
    - Newline handling (LF, CRLF, bare CR).
    - peek() with default and custom offsets.
    - advance() semantics.
    - eof() detection.
    - line tracking.
    - column tracking.
    - offset tracking.
    - ScannerError for invalid construction and peek.

Dependencies:
    - :mod:`app.parser.lexer.scanner`            — subject under test.
    - :mod:`app.parser.lexer.scanner_exceptions` — ScannerError.
    - :mod:`pytest`                              — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.parser.lexer.scanner import CharacterScanner
from app.parser.lexer.scanner_exceptions import ScannerError

# ---------------------------------------------------------------------------
# Empty source
# ---------------------------------------------------------------------------


class TestEmptySource:
    """Scanner behaviour when constructed with an empty string."""

    def test_eof_immediately(self) -> None:
        """eof() is True for empty source."""
        scanner = CharacterScanner("")
        assert scanner.eof() is True

    def test_current_returns_none(self) -> None:
        """current() returns None for empty source."""
        scanner = CharacterScanner("")
        assert scanner.current() is None

    def test_advance_returns_none(self) -> None:
        """advance() returns None for empty source."""
        scanner = CharacterScanner("")
        assert scanner.advance() is None

    def test_peek_returns_none(self) -> None:
        """peek() returns None for empty source."""
        scanner = CharacterScanner("")
        assert scanner.peek() is None

    def test_initial_line(self) -> None:
        """line starts at 1 for empty source."""
        assert CharacterScanner("").line == 1

    def test_initial_column(self) -> None:
        """column starts at 1 for empty source."""
        assert CharacterScanner("").column == 1

    def test_initial_offset(self) -> None:
        """offset starts at 0 for empty source."""
        assert CharacterScanner("").offset == 0


# ---------------------------------------------------------------------------
# Single character
# ---------------------------------------------------------------------------


class TestSingleCharacter:
    """Scanner behaviour over a one-character source string."""

    def test_current_returns_char(self) -> None:
        """current() returns the single character before advancing."""
        scanner = CharacterScanner("X")
        assert scanner.current() == "X"

    def test_not_eof_initially(self) -> None:
        """eof() is False before advancing past the single character."""
        scanner = CharacterScanner("X")
        assert scanner.eof() is False

    def test_advance_makes_eof(self) -> None:
        """advance() past the only character causes eof()."""
        scanner = CharacterScanner("X")
        scanner.advance()
        assert scanner.eof() is True

    def test_advance_returns_none_at_end(self) -> None:
        """advance() returns None when moving past the last character."""
        scanner = CharacterScanner("X")
        result = scanner.advance()
        assert result is None

    def test_current_after_advance_is_none(self) -> None:
        """current() returns None after advancing past the only character."""
        scanner = CharacterScanner("X")
        scanner.advance()
        assert scanner.current() is None

    def test_offset_after_advance(self) -> None:
        """offset is 1 after advancing past the only character."""
        scanner = CharacterScanner("X")
        scanner.advance()
        assert scanner.offset == 1


# ---------------------------------------------------------------------------
# Multiple characters
# ---------------------------------------------------------------------------


class TestMultipleCharacters:
    """Scanner behaviour over multi-character source strings."""

    def test_iterates_all_characters(self) -> None:
        """Advancing through the source visits every character in order."""
        source = "HELLO"
        scanner = CharacterScanner(source)
        collected: list[str] = []

        while not scanner.eof():
            ch = scanner.current()
            assert ch is not None
            collected.append(ch)
            scanner.advance()

        assert collected == list(source)

    def test_advance_returns_next_char(self) -> None:
        """advance() returns the character now at the cursor."""
        scanner = CharacterScanner("AB")
        result = scanner.advance()
        assert result == "B"

    def test_advance_sequence(self) -> None:
        """Repeated advance() calls step through all characters."""
        scanner = CharacterScanner("ABC")
        assert scanner.current() == "A"
        assert scanner.advance() == "B"
        assert scanner.advance() == "C"
        assert scanner.advance() is None
        assert scanner.eof() is True

    def test_offset_increments(self) -> None:
        """offset increments by 1 with each advance() call."""
        scanner = CharacterScanner("ABC")
        assert scanner.offset == 0
        scanner.advance()
        assert scanner.offset == 1
        scanner.advance()
        assert scanner.offset == 2


# ---------------------------------------------------------------------------
# peek()
# ---------------------------------------------------------------------------


class TestPeek:
    """peek() method behaviour."""

    def test_peek_default_is_next(self) -> None:
        """peek() with no argument looks one character ahead."""
        scanner = CharacterScanner("AB")
        assert scanner.peek() == "B"

    def test_peek_zero_is_current(self) -> None:
        """peek(0) returns the current character."""
        scanner = CharacterScanner("AB")
        assert scanner.peek(0) == "A"

    def test_peek_does_not_advance(self) -> None:
        """peek() does not move the cursor."""
        scanner = CharacterScanner("AB")
        scanner.peek()
        assert scanner.current() == "A"

    def test_peek_multiple_offsets(self) -> None:
        """peek() can look an arbitrary number of positions ahead."""
        scanner = CharacterScanner("ABCDE")
        assert scanner.peek(0) == "A"
        assert scanner.peek(1) == "B"
        assert scanner.peek(2) == "C"
        assert scanner.peek(3) == "D"
        assert scanner.peek(4) == "E"

    def test_peek_past_end_returns_none(self) -> None:
        """peek() returns None when the target is at or past EOF."""
        scanner = CharacterScanner("A")
        assert scanner.peek(1) is None
        assert scanner.peek(100) is None

    def test_peek_negative_raises(self) -> None:
        """peek() raises ScannerError for negative offsets."""
        scanner = CharacterScanner("A")
        with pytest.raises(ScannerError):
            scanner.peek(-1)

    def test_peek_after_advance(self) -> None:
        """peek() works correctly after the cursor has been moved."""
        scanner = CharacterScanner("ABC")
        scanner.advance()  # cursor now on 'B'
        assert scanner.peek() == "C"
        assert scanner.peek(0) == "B"


# ---------------------------------------------------------------------------
# eof()
# ---------------------------------------------------------------------------


class TestEof:
    """eof() detection."""

    def test_eof_empty_source(self) -> None:
        """eof() is True immediately for empty source."""
        assert CharacterScanner("").eof() is True

    def test_not_eof_with_chars(self) -> None:
        """eof() is False while characters remain."""
        assert CharacterScanner("X").eof() is False

    def test_eof_after_full_traversal(self) -> None:
        """eof() becomes True after consuming all characters."""
        scanner = CharacterScanner("XY")
        scanner.advance()
        scanner.advance()
        assert scanner.eof() is True

    def test_advance_beyond_eof_is_safe(self) -> None:
        """advance() beyond EOF is safe and returns None repeatedly."""
        scanner = CharacterScanner("X")
        scanner.advance()
        assert scanner.advance() is None
        assert scanner.advance() is None
        assert scanner.eof() is True


# ---------------------------------------------------------------------------
# Line tracking
# ---------------------------------------------------------------------------


class TestLineTracking:
    """line counter behaviour."""

    def test_initial_line_is_1(self) -> None:
        """line starts at 1."""
        assert CharacterScanner("HELLO").line == 1

    def test_line_increments_on_lf(self) -> None:
        """line increments when advance() passes a LF character."""
        scanner = CharacterScanner("A\nB")
        assert scanner.line == 1
        scanner.advance()  # consume 'A'
        scanner.advance()  # consume '\n' → line becomes 2
        assert scanner.line == 2

    def test_line_increments_on_cr(self) -> None:
        """line increments when advance() passes a bare CR character."""
        scanner = CharacterScanner("A\rB")
        scanner.advance()  # consume 'A'
        scanner.advance()  # consume '\r' → line becomes 2
        assert scanner.line == 2

    def test_crlf_counts_as_one_newline(self) -> None:
        """CRLF sequence increments line by exactly 1."""
        scanner = CharacterScanner("A\r\nB")
        scanner.advance()  # consume 'A'
        scanner.advance()  # consume '\r' → line 2
        scanner.advance()  # consume '\n' → should NOT increment again
        assert scanner.line == 2

    def test_multiple_newlines(self) -> None:
        """Multiple newlines accumulate correctly."""
        scanner = CharacterScanner("A\nB\nC")
        for _ in range(4):
            scanner.advance()
        # Consumed A, \n, B, \n  → line = 3
        assert scanner.line == 3

    def test_line_does_not_increment_on_regular_char(self) -> None:
        """line does not change when advancing over non-newline chars."""
        scanner = CharacterScanner("ABC")
        scanner.advance()
        scanner.advance()
        assert scanner.line == 1


# ---------------------------------------------------------------------------
# Column tracking
# ---------------------------------------------------------------------------


class TestColumnTracking:
    """column counter behaviour."""

    def test_initial_column_is_1(self) -> None:
        """column starts at 1."""
        assert CharacterScanner("HELLO").column == 1

    def test_column_increments_on_advance(self) -> None:
        """column increments each time advance() is called on a non-newline."""
        scanner = CharacterScanner("ABC")
        assert scanner.column == 1
        scanner.advance()  # consume 'A'
        assert scanner.column == 2
        scanner.advance()  # consume 'B'
        assert scanner.column == 3

    def test_column_resets_after_lf(self) -> None:
        """column resets to 1 after a LF newline."""
        scanner = CharacterScanner("AB\nC")
        scanner.advance()  # consume 'A' → col 2
        scanner.advance()  # consume 'B' → col 3
        scanner.advance()  # consume '\n' → line 2, col 1
        assert scanner.column == 1

    def test_column_resets_after_cr(self) -> None:
        """column resets to 1 after a bare CR."""
        scanner = CharacterScanner("AB\rC")
        scanner.advance()
        scanner.advance()
        scanner.advance()  # consume '\r'
        assert scanner.column == 1

    def test_column_after_crlf(self) -> None:
        """column is 1 after a CRLF sequence, then increments normally."""
        scanner = CharacterScanner("A\r\nB")
        scanner.advance()  # consume 'A' → col 2
        scanner.advance()  # consume '\r' → col 1, line 2
        scanner.advance()  # consume '\n' → still col 1 (absorbed)
        assert scanner.column == 1
        scanner.advance()  # consume 'B' → col 2
        assert scanner.column == 2


# ---------------------------------------------------------------------------
# Offset tracking
# ---------------------------------------------------------------------------


class TestOffsetTracking:
    """offset counter behaviour."""

    def test_initial_offset_is_0(self) -> None:
        """offset starts at 0."""
        assert CharacterScanner("ABC").offset == 0

    def test_offset_increments_with_advance(self) -> None:
        """offset increments by exactly 1 per advance() call."""
        scanner = CharacterScanner("ABCDE")
        for expected in range(1, 6):
            scanner.advance()
            assert scanner.offset == expected

    def test_offset_at_eof(self) -> None:
        """offset equals len(source) when eof() is True."""
        source = "HELLO"
        scanner = CharacterScanner(source)
        for _ in source:
            scanner.advance()
        assert scanner.offset == len(source)
        assert scanner.eof() is True

    def test_offset_does_not_change_on_peek(self) -> None:
        """peek() does not change the offset."""
        scanner = CharacterScanner("ABC")
        scanner.peek(2)
        assert scanner.offset == 0


# ---------------------------------------------------------------------------
# Invalid construction
# ---------------------------------------------------------------------------


class TestInvalidConstruction:
    """ScannerError raised for invalid constructor arguments."""

    def test_bytes_raises(self) -> None:
        """Passing bytes raises ScannerError."""
        with pytest.raises(ScannerError):
            CharacterScanner(b"hello")  # type: ignore[arg-type]

    def test_none_raises(self) -> None:
        """Passing None raises ScannerError."""
        with pytest.raises(ScannerError):
            CharacterScanner(None)  # type: ignore[arg-type]

    def test_int_raises(self) -> None:
        """Passing an int raises ScannerError."""
        with pytest.raises(ScannerError):
            CharacterScanner(42)  # type: ignore[arg-type]

    def test_error_message_non_empty(self) -> None:
        """ScannerError carries a non-empty message."""
        with pytest.raises(ScannerError) as exc_info:
            CharacterScanner(None)  # type: ignore[arg-type]
        assert exc_info.value.message
