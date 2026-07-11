"""
File Type Classifier.

Purpose:
    Classify a discovered file into a :class:`app.workspace.models.FileType`
    based purely on its extension and, when necessary, a lightweight
    content sniff — without implementing any parser logic.

Responsibilities:
    - Map well-known mainframe extensions to their canonical type.
    - Fall back to content-based disambiguation for ambiguous extensions
      (e.g. ``.txt`` files that look like JCL or BMS source).
    - Always return one of the :class:`~app.workspace.models.FileType`
      enum members.
    - Never parse program logic — only classify.

Dependencies:
    - app.workspace.models — :class:`FileType`
    - app.core.logging     — Loguru logger

Examples:
    Classifying a file by name and optional content::

        from app.workspace.classifier import FileClassifier

        clf = FileClassifier()
        ft = clf.classify(filename="payroll.cbl", content=None)
        # -> FileType.COBOL

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.core.logging import logger
from app.workspace.models import FileType

__all__ = ["FileClassifier"]

# ---------------------------------------------------------------------------
# Extension → FileType mapping (primary lookup)
# ---------------------------------------------------------------------------

_EXT_MAP: dict[str, FileType] = {
    ".cbl": FileType.COBOL,
    ".cob": FileType.COBOL,
    ".cpy": FileType.COPYBOOK,
    ".jcl": FileType.JCL,
    ".proc": FileType.PROC,
    ".prc": FileType.PROC,
    ".bms": FileType.BMS,
    ".xml": FileType.XML,
    ".json": FileType.JSON,
    ".txt": FileType.TEXT,
}

# ---------------------------------------------------------------------------
# Content sniff signatures (bytes prefix checks)
# ---------------------------------------------------------------------------

# JCL jobs start with //jobname  JOB  or //stepname EXEC
_JCL_PREFIX: bytes = b"//"
# BMS definitions start with a print character then spaces then BMS keywords
_BMS_KEYWORDS: list[bytes] = [b"DFHMSD", b"DFHMDI", b"DFHMDF"]


class FileClassifier:
    """
    Stateless file type classifier for mainframe workspace files.

    Classification is performed in two stages:

    1. **Extension lookup** — deterministic; covers the majority of cases.
    2. **Content sniff** — applied only when the extension is ``.txt``
       or absent, to disambiguate files whose type is not encoded in their
       name (common in legacy mainframe archives).
    """

    def classify(
        self,
        filename: str,
        content: bytes | None = None,
    ) -> FileType:
        """
        Classify *filename* into a :class:`FileType`.

        Args:
            filename: The basename of the file (e.g. ``"payroll.cbl"``).
            content:  Optional raw bytes of the file.  When provided and
                      the extension is ``.txt`` or absent, a lightweight
                      content sniff is used for disambiguation.

        Returns:
            The :class:`~app.workspace.models.FileType` for this file.

        Examples:
            >>> clf = FileClassifier()
            >>> clf.classify("payroll.cbl")
            <FileType.COBOL: 'COBOL'>
            >>> clf.classify("batch.txt", b"//MYJOB JOB ...")
            <FileType.JCL: 'JCL'>
        """
        ext = self._extract_extension(filename)
        file_type = _EXT_MAP.get(ext)

        if file_type is not None and file_type != FileType.TEXT:
            logger.debug(
                "FileClassifier: '{}' classified as {} via extension '{}'.",
                filename,
                file_type.value,
                ext,
            )
            return file_type

        # For .txt or unrecognised extensions, attempt a content sniff
        if content is not None:
            sniffed = self._sniff_content(content)
            if sniffed is not None:
                logger.debug(
                    "FileClassifier: '{}' classified as {} via content sniff.",
                    filename,
                    sniffed.value,
                )
                return sniffed

        # Return TEXT for .txt with no distinctive content, otherwise UNKNOWN
        if file_type == FileType.TEXT:
            return FileType.TEXT

        logger.debug(
            "FileClassifier: '{}' (ext='{}') classified as UNKNOWN.",
            filename,
            ext,
        )
        return FileType.UNKNOWN

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_extension(filename: str) -> str:
        """
        Extract the lowercase dot-prefixed extension from *filename*.

        Args:
            filename: Full filename string.

        Returns:
            Lowercase extension string including the dot, or ``""`` when
            no extension is present.
        """
        idx = filename.rfind(".")
        if idx == -1 or idx == len(filename) - 1:
            return ""
        return filename[idx:].lower()

    @staticmethod
    def _sniff_content(content: bytes) -> FileType | None:
        """
        Apply a lightweight byte-pattern sniff to identify the file type.

        Only called when the extension alone is insufficient for
        classification.  Checks a small prefix of the content.

        Args:
            content: Raw file bytes (may be empty).

        Returns:
            A :class:`~app.workspace.models.FileType` if a signature is
            matched, or ``None`` when no match is found.
        """
        if not content:
            return None

        # Use only the first 4 KB for performance — never parse the whole file
        sample = content[:4096].lstrip()

        # JCL detection: starts with //
        if sample.startswith(_JCL_PREFIX):
            return FileType.JCL

        # BMS detection: contains BMS macro names in the first sample
        upper_sample = sample.upper()
        if any(kw in upper_sample for kw in _BMS_KEYWORDS):
            return FileType.BMS

        return None
