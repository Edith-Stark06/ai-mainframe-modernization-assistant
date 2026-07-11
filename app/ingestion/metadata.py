"""
File Metadata Extractor.

Purpose:
    Extract and assemble structured metadata from a validated file's
    raw bytes and name, ready for storage alongside the ingested file.

Responsibilities:
    - Compute the SHA-256 hex digest of the raw file bytes.
    - Delegate encoding detection to :class:`app.ingestion.detector.EncodingDetector`.
    - Assemble and return a :class:`app.ingestion.models.FileMetadata` record.
    - Log every extraction at DEBUG level.

Dependencies:
    - hashlib               — SHA-256 digest computation
    - app.ingestion.detector — :class:`EncodingDetector`
    - app.ingestion.models  — :class:`FileMetadata`
    - app.core.logging      — Loguru logger

Examples:
    Extracting metadata from a raw file::

        from app.ingestion.metadata import MetadataExtractor

        extractor = MetadataExtractor()
        meta = extractor.extract(
            filename="payroll.cbl",
            content=b"IDENTIFICATION DIVISION.",
            workspace_id="ws-uuid",
        )
        print(meta.sha256)
        print(meta.encoding)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import hashlib

from app.core.logging import logger
from app.ingestion.detector import EncodingDetector
from app.ingestion.models import FileMetadata

__all__ = ["MetadataExtractor"]


class MetadataExtractor:
    """
    Extracts file metadata from raw bytes and filename.

    Attributes:
        _detector: Shared :class:`EncodingDetector` instance used for
                   every extraction call.
    """

    def __init__(self) -> None:
        """Initialise the extractor with a shared encoding detector."""
        self._detector = EncodingDetector()

    def extract(
        self,
        filename: str,
        content: bytes,
        workspace_id: str,
    ) -> FileMetadata:
        """
        Extract and return structured metadata for a single file.

        Args:
            filename:     Original filename supplied by the client.
            content:      Raw file bytes (already validated).
            workspace_id: UUID4 string of the parent workspace.

        Returns:
            A fully populated :class:`~app.ingestion.models.FileMetadata`
            instance ready for persistence.

        Examples:
            >>> extractor = MetadataExtractor()
            >>> meta = extractor.extract("a.cbl", b"DATA", "ws-001")
            >>> isinstance(meta.sha256, str) and len(meta.sha256) == 64
            True
        """
        extension = self._extract_extension(filename)
        sha256 = self._compute_sha256(content)
        encoding = self._detector.detect(content)
        size = len(content)

        logger.debug(
            "MetadataExtractor: '{}' | ext={} | size={} | sha256={}...{} | enc={}",
            filename,
            extension,
            size,
            sha256[:8],
            sha256[-4:],
            encoding,
        )

        return FileMetadata(
            filename=filename,
            extension=extension,
            size_bytes=size,
            sha256=sha256,
            encoding=encoding,
            workspace_id=workspace_id,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_sha256(content: bytes) -> str:
        """
        Compute and return the hex-encoded SHA-256 digest of *content*.

        Args:
            content: Raw bytes to hash.

        Returns:
            Lowercase hex string of the 256-bit digest (64 characters).
        """
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _extract_extension(filename: str) -> str:
        """
        Extract the lowercase dot-prefixed extension from *filename*.

        Args:
            filename: Full filename string.

        Returns:
            Lowercase extension (e.g. ``".cbl"``), or ``""`` if absent.
        """
        idx = filename.rfind(".")
        if idx == -1 or idx == len(filename) - 1:
            return ""
        return filename[idx:].lower()
