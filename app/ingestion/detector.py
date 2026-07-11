"""
File Encoding Detector.

Purpose:
    Detect the character encoding of raw file content, with first-class
    support for encodings common in IBM Z mainframe environments.

Responsibilities:
    - Detect BOM-prefixed encodings (UTF-16 LE/BE, UTF-8 BOM).
    - Detect EBCDIC via heuristic byte distribution analysis.
    - Delegate to ``chardet`` for probabilistic ASCII / UTF-8 detection.
    - Always return one of the canonical ``DetectedEncoding`` literals.
    - Never raise; fall back to ``\"UNKNOWN\"`` on unexpected input.

Dependencies:
    - chardet              — probabilistic encoding detection library
    - app.ingestion.models — :data:`DetectedEncoding` literal type
    - app.core.logging     — Loguru logger

Examples:
    Detecting the encoding of a byte string::

        from app.ingestion.detector import EncodingDetector

        detector = EncodingDetector()
        encoding = detector.detect(b"IDENTIFICATION DIVISION.")
        # -> "UTF-8" or "ASCII"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import chardet

from app.core.logging import logger
from app.ingestion.models import DetectedEncoding

__all__ = ["EncodingDetector"]

# ---------------------------------------------------------------------------
# EBCDIC heuristic constants
# ---------------------------------------------------------------------------

# These byte ranges are characteristic of EBCDIC-encoded text.
# Printable EBCDIC characters fall between 0x40 and 0xFF, with the
# range 0x00–0x3F reserved for control codes.
_EBCDIC_PRINTABLE_LOW = 0x40
_EBCDIC_PRINTABLE_HIGH = 0xFF
# Bytes that are NUL-adjacent and unprintable in ASCII but common in EBCDIC
_EBCDIC_CONTROL_MAX = 0x3F
# Threshold: if this fraction of bytes are in the EBCDIC-specific zone
# and not valid ASCII printables, we call it EBCDIC.
_EBCDIC_THRESHOLD = 0.10

# ---------------------------------------------------------------------------
# BOM signatures
# ---------------------------------------------------------------------------

_BOM_UTF16_LE = b"\xff\xfe"
_BOM_UTF16_BE = b"\xfe\xff"
_BOM_UTF8 = b"\xef\xbb\xbf"


class EncodingDetector:
    """
    Stateless encoding detector for mainframe file content.

    Detection priority order
    ------------------------
    1. UTF-16 BOM (little-endian or big-endian).
    2. UTF-8 BOM.
    3. EBCDIC heuristic.
    4. ``chardet`` probabilistic detection (ASCII / UTF-8).
    5. Fallback → ``"UNKNOWN"``.
    """

    def detect(self, content: bytes) -> DetectedEncoding:
        """
        Detect the encoding of *content* and return a canonical label.

        Args:
            content: Raw file bytes to analyse.

        Returns:
            One of ``"UTF-8"``, ``"ASCII"``, ``"UTF-16"``, ``"EBCDIC"``,
            or ``"UNKNOWN"``.

        Examples:
            >>> detector = EncodingDetector()
            >>> detector.detect(b"\\xff\\xfeH\\x00i\\x00")
            'UTF-16'
        """
        if not content:
            logger.debug("EncodingDetector: empty content, returning UNKNOWN.")
            return "UNKNOWN"

        try:
            # ------------------------------------------------------------------
            # 1. BOM-based detection (most reliable)
            # ------------------------------------------------------------------
            if content[:2] in (_BOM_UTF16_LE, _BOM_UTF16_BE):
                logger.debug("EncodingDetector: UTF-16 BOM detected.")
                return "UTF-16"

            if content[:3] == _BOM_UTF8:
                logger.debug("EncodingDetector: UTF-8 BOM detected.")
                return "UTF-8"

            # ------------------------------------------------------------------
            # 2. EBCDIC heuristic
            # ------------------------------------------------------------------
            if self._is_ebcdic(content):
                logger.debug("EncodingDetector: EBCDIC heuristic matched.")
                return "EBCDIC"

            # ------------------------------------------------------------------
            # 3. chardet probabilistic detection
            # ------------------------------------------------------------------
            result = chardet.detect(content)
            detected: str | None = result.get("encoding")
            confidence: float = float(result.get("confidence") or 0.0)

            logger.debug(
                "EncodingDetector: chardet detected '{}' with confidence {:.2f}.",
                detected,
                confidence,
            )

            if detected is None:
                return "UNKNOWN"

            normalized = detected.upper().replace("-", "")
            if "ASCII" in normalized:
                return "ASCII"
            if "UTF8" in normalized or "UTF-8" in detected.upper():
                return "UTF-8"
            if "UTF16" in normalized or "UTF-16" in detected.upper():
                return "UTF-16"

            return "UNKNOWN"

        except Exception as exc:  # pragma: no cover
            logger.warning(
                "EncodingDetector: unexpected error during detection: {}. "
                "Falling back to UNKNOWN.",
                exc,
            )
            return "UNKNOWN"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_ebcdic(content: bytes) -> bool:
        """
        Apply a byte-distribution heuristic to identify EBCDIC content.

        EBCDIC text typically has a high proportion of bytes in the
        0x40–0xFF range that are not valid ASCII printables, and a
        notable presence of bytes in the 0x00–0x3F control range that
        differ from ASCII's control layout.

        Args:
            content: Raw file bytes.

        Returns:
            ``True`` if the content is likely EBCDIC, ``False`` otherwise.
        """
        if len(content) < 8:
            return False

        sample = content[:4096]
        total = len(sample)

        # Count bytes that are valid ASCII printables (0x20–0x7E)
        ascii_printable = sum(0x20 <= b <= 0x7E for b in sample)
        # Count high bytes that appear in EBCDIC but not in ASCII
        high_bytes = sum(b > 0x7E for b in sample)
        # Count low control bytes (0x00–0x1F), excluding newlines (0x0A, 0x0D)
        control_bytes = sum(b < 0x20 and b not in (0x09, 0x0A, 0x0D) for b in sample)

        ascii_ratio = ascii_printable / total
        high_ratio = high_bytes / total
        control_ratio = control_bytes / total

        # Heuristic: EBCDIC content has few ASCII printables, many high bytes,
        # and possibly many low control bytes.
        return ascii_ratio < 0.50 and (high_ratio + control_ratio) > _EBCDIC_THRESHOLD
