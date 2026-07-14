"""
Tests for the COBOL Source Reader.

Purpose:
    Verify that :class:`~app.parser.lexer.source_reader.SourceReader`
    correctly reads and decodes COBOL source files encoded in the three
    supported encodings, and raises structured errors for unsupported
    encodings and missing files.

Responsibilities:
    - UTF-8 encoding round-trip test.
    - UTF-8 with BOM encoding round-trip test.
    - ASCII encoding round-trip test.
    - Missing file error test.
    - Unsupported encoding error test.

Dependencies:
    - :mod:`app.parser.lexer.source_reader` — subject under test.
    - :mod:`pytest`                          — test framework.
    - :mod:`pathlib`                         — temporary path helpers.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from pathlib import Path

from app.parser.lexer.source_reader import SourceReader, SourceReaderError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COBOL_SNIPPET = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. HELLO-WORLD.\n"
    "       PROCEDURE DIVISION.\n"
    "           DISPLAY 'HELLO, WORLD!'.\n"
    "           STOP RUN.\n"
)


# ---------------------------------------------------------------------------
# UTF-8
# ---------------------------------------------------------------------------


class TestUtf8:
    """Source files encoded in plain UTF-8."""

    def test_read_returns_string(self, tmp_path: Path) -> None:
        """read() returns a str for a valid UTF-8 file."""
        source_file = tmp_path / "hello.cbl"
        source_file.write_bytes(_COBOL_SNIPPET.encode("utf-8"))

        reader = SourceReader()
        result = reader.read(source_file)

        assert isinstance(result, str)

    def test_content_preserved_exactly(self, tmp_path: Path) -> None:
        """read() preserves the exact source text for UTF-8 files."""
        source_file = tmp_path / "hello.cbl"
        source_file.write_bytes(_COBOL_SNIPPET.encode("utf-8"))

        reader = SourceReader()
        result = reader.read(source_file)

        assert result == _COBOL_SNIPPET

    def test_non_ascii_utf8_characters(self, tmp_path: Path) -> None:
        """read() correctly decodes non-ASCII UTF-8 characters."""
        content = "       * Ação de COBOL — täst\n"
        source_file = tmp_path / "unicode.cbl"
        source_file.write_bytes(content.encode("utf-8"))

        reader = SourceReader()
        result = reader.read(source_file)

        assert result == content


# ---------------------------------------------------------------------------
# UTF-8 BOM
# ---------------------------------------------------------------------------


class TestUtf8Bom:
    """Source files encoded in UTF-8 with a Byte Order Mark (BOM)."""

    def test_read_returns_string(self, tmp_path: Path) -> None:
        """read() returns a str for a valid UTF-8 BOM file."""
        source_file = tmp_path / "bom.cbl"
        source_file.write_bytes(_COBOL_SNIPPET.encode("utf-8-sig"))

        reader = SourceReader()
        result = reader.read(source_file)

        assert isinstance(result, str)

    def test_bom_is_stripped(self, tmp_path: Path) -> None:
        """read() strips the UTF-8 BOM so the result starts with the first character."""
        source_file = tmp_path / "bom.cbl"
        source_file.write_bytes(_COBOL_SNIPPET.encode("utf-8-sig"))

        reader = SourceReader()
        result = reader.read(source_file)

        # The BOM (U+FEFF) must not appear in the returned string.
        assert not result.startswith("\ufeff")

    def test_content_preserved_after_bom_strip(self, tmp_path: Path) -> None:
        """read() returns the correct source content after BOM removal."""
        source_file = tmp_path / "bom.cbl"
        source_file.write_bytes(_COBOL_SNIPPET.encode("utf-8-sig"))

        reader = SourceReader()
        result = reader.read(source_file)

        assert result == _COBOL_SNIPPET


# ---------------------------------------------------------------------------
# ASCII
# ---------------------------------------------------------------------------


class TestAscii:
    """Source files encoded in pure ASCII."""

    def test_read_returns_string(self, tmp_path: Path) -> None:
        """read() returns a str for a valid ASCII file."""
        source_file = tmp_path / "ascii.cbl"
        source_file.write_bytes(_COBOL_SNIPPET.encode("ascii"))

        reader = SourceReader()
        result = reader.read(source_file)

        assert isinstance(result, str)

    def test_content_preserved_exactly(self, tmp_path: Path) -> None:
        """read() preserves the exact source text for ASCII files."""
        source_file = tmp_path / "ascii.cbl"
        source_file.write_bytes(_COBOL_SNIPPET.encode("ascii"))

        reader = SourceReader()
        result = reader.read(source_file)

        assert result == _COBOL_SNIPPET

    def test_empty_file(self, tmp_path: Path) -> None:
        """read() returns an empty string for a zero-byte ASCII file."""
        source_file = tmp_path / "empty.cbl"
        source_file.write_bytes(b"")

        reader = SourceReader()
        result = reader.read(source_file)

        assert result == ""


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


class TestMissingFile:
    """Behaviour when the supplied path does not exist."""

    def test_raises_source_reader_error(self, tmp_path: Path) -> None:
        """read() raises SourceReaderError for a non-existent path."""
        missing = tmp_path / "does_not_exist.cbl"

        reader = SourceReader()
        with pytest.raises(SourceReaderError):
            reader.read(missing)

    def test_error_references_path(self, tmp_path: Path) -> None:
        """SourceReaderError.path contains the missing path."""
        missing = tmp_path / "missing.cbl"

        reader = SourceReader()
        with pytest.raises(SourceReaderError) as exc_info:
            reader.read(missing)

        assert exc_info.value.path == missing

    def test_error_message_meaningful(self, tmp_path: Path) -> None:
        """SourceReaderError carries a non-empty message string."""
        missing = tmp_path / "missing.cbl"

        reader = SourceReader()
        with pytest.raises(SourceReaderError) as exc_info:
            reader.read(missing)

        assert exc_info.value.message


# ---------------------------------------------------------------------------
# Unsupported encoding
# ---------------------------------------------------------------------------


class TestUnsupportedEncoding:
    """Behaviour when the file is encoded in an unsupported encoding."""

    def test_raises_source_reader_error_for_latin1(self, tmp_path: Path) -> None:
        """read() raises SourceReaderError for a Latin-1 file with non-ASCII bytes."""
        # Write bytes that are valid Latin-1 but invalid UTF-8.
        # 0xE9 is 'é' in Latin-1 and is an invalid continuation byte in UTF-8.
        content = b"       PROGRAM-ID. T\xe9ST.\n"
        source_file = tmp_path / "latin1.cbl"
        source_file.write_bytes(content)

        reader = SourceReader()
        with pytest.raises(SourceReaderError):
            reader.read(source_file)

    def test_raises_source_reader_error_for_arbitrary_binary(
        self, tmp_path: Path
    ) -> None:
        """read() raises SourceReaderError for arbitrary binary data."""
        content = bytes(range(128, 256))
        source_file = tmp_path / "binary.cbl"
        source_file.write_bytes(content)

        reader = SourceReader()
        with pytest.raises(SourceReaderError):
            reader.read(source_file)

    def test_error_references_path(self, tmp_path: Path) -> None:
        """SourceReaderError.path is the path of the undecodable file."""
        content = b"\xff\xfe\x00\x01\x00\x02"  # Not valid UTF-8 or ASCII.
        source_file = tmp_path / "bad_encoding.cbl"
        source_file.write_bytes(content)

        reader = SourceReader()
        with pytest.raises(SourceReaderError) as exc_info:
            reader.read(source_file)

        assert exc_info.value.path == source_file
