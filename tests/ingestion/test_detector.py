"""
Encoding Detector Tests.

Purpose:
    Verify that :class:`app.ingestion.detector.EncodingDetector` correctly
    identifies UTF-8, ASCII, UTF-16 (via BOM), EBCDIC (via heuristic),
    and falls back to UNKNOWN for unrecognised content.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest

from app.ingestion.detector import EncodingDetector


@pytest.fixture()
def detector() -> EncodingDetector:
    """Return an :class:`EncodingDetector` instance."""
    return EncodingDetector()


# ---------------------------------------------------------------------------
# BOM-based detection
# ---------------------------------------------------------------------------


class TestBOMDetection:
    """Tests for BOM-prefix encoding detection."""

    def test_utf16_le_bom_detected(self, detector: EncodingDetector) -> None:
        """UTF-16 LE BOM prefix must return 'UTF-16'."""
        content = b"\xff\xfe" + "Hello".encode("utf-16-le")
        assert detector.detect(content) == "UTF-16"

    def test_utf16_be_bom_detected(self, detector: EncodingDetector) -> None:
        """UTF-16 BE BOM prefix must return 'UTF-16'."""
        content = b"\xfe\xff" + "Hello".encode("utf-16-be")
        assert detector.detect(content) == "UTF-16"

    def test_utf8_bom_detected(self, detector: EncodingDetector) -> None:
        """UTF-8 BOM prefix must return 'UTF-8'."""
        content = b"\xef\xbb\xbf" + b"IDENTIFICATION DIVISION."
        assert detector.detect(content) == "UTF-8"


# ---------------------------------------------------------------------------
# EBCDIC heuristic
# ---------------------------------------------------------------------------


class TestEBCDICDetection:
    """Tests for the EBCDIC byte-distribution heuristic."""

    def test_high_byte_content_detected_as_ebcdic(
        self, detector: EncodingDetector
    ) -> None:
        """
        Content dominated by bytes > 0x7E and < 0x20 control codes must
        be detected as EBCDIC.
        """
        # Typical EBCDIC printable range 0xC0-0xFF with some control codes
        content = bytes([0xC9, 0xC4, 0xD5, 0x40, 0xE5, 0xD9, 0x00, 0x01] * 200)
        result = detector.detect(content)
        assert result == "EBCDIC"

    def test_ascii_text_not_detected_as_ebcdic(
        self, detector: EncodingDetector
    ) -> None:
        """Plain ASCII text must not be mis-identified as EBCDIC."""
        content = b"IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST.\n"
        result = detector.detect(content)
        assert result != "EBCDIC"


# ---------------------------------------------------------------------------
# ASCII / UTF-8 chardet path
# ---------------------------------------------------------------------------


class TestChardetDetection:
    """Tests for the chardet-delegated detection path."""

    def test_ascii_content_detected(self, detector: EncodingDetector) -> None:
        """Plain ASCII content must return 'ASCII' or 'UTF-8'."""
        content = b"IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO.\n"
        result = detector.detect(content)
        assert result in {"ASCII", "UTF-8"}

    def test_utf8_content_detected(self, detector: EncodingDetector) -> None:
        """UTF-8 encoded content must return 'UTF-8'."""
        content = "IDENTIFICATION DIVISION.".encode("utf-8")
        result = detector.detect(content)
        assert result in {"UTF-8", "ASCII"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEncodingDetectorEdgeCases:
    """Tests for edge cases and fallback behaviour."""

    def test_empty_bytes_returns_unknown(self, detector: EncodingDetector) -> None:
        """Empty byte string must return 'UNKNOWN'."""
        result = detector.detect(b"")
        assert result == "UNKNOWN"

    def test_single_byte_does_not_raise(self, detector: EncodingDetector) -> None:
        """Single-byte input must not raise."""
        result = detector.detect(b"\x00")
        assert isinstance(result, str)

    def test_return_type_is_string(self, detector: EncodingDetector) -> None:
        """detect() must always return a string regardless of input."""
        for sample in [b"", b"hello", b"\xff\xfe", b"\x00\x01\x02"]:
            result = detector.detect(sample)
            assert isinstance(result, str)

    def test_valid_return_values(self, detector: EncodingDetector) -> None:
        """All return values must be from the canonical encoding set."""
        valid = {"UTF-8", "ASCII", "UTF-16", "EBCDIC", "UNKNOWN"}
        for sample in [
            b"",
            b"hello world",
            b"\xff\xfehello",
            b"\xfe\xffhello",
            b"\xef\xbb\xbfhello",
        ]:
            assert detector.detect(sample) in valid
