"""
COBOL Source Reader.

Purpose:
    Provide the first stage of the COBOL parser pipeline: reading a COBOL
    source file from disk and returning its contents as a plain Python string.

Responsibilities:
    - Accept a :class:`pathlib.Path` pointing to a COBOL source file.
    - Detect and decode UTF-8, UTF-8 BOM, and ASCII encoded files.
    - Preserve the original source text exactly as it appears on disk.
    - Raise :class:`SourceReaderError` for unsupported encodings or missing
      files so that callers receive structured, typed exceptions.

Non-responsibilities:
    - Format detection (fixed, free, or variable) — implemented in Task-007.
    - Normalisation, scanning, lexing, or parsing.
    - Any COBOL semantic knowledge.

Dependencies:
    - Python standard library only (``pathlib``, ``codecs``).

Examples:
    Reading a UTF-8 COBOL source file::

        from pathlib import Path
        from app.parser.lexer.source_reader import SourceReader

        reader = SourceReader()
        source = reader.read(Path("program.cbl"))

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import codecs
from pathlib import Path

from loguru import logger

__all__ = ["SourceReader", "SourceReaderError"]

# ---------------------------------------------------------------------------
# Supported encodings, in probe order.
# UTF-8-SIG handles UTF-8 BOM transparently by stripping the BOM before
# decoding, so the returned string is always BOM-free.
# ASCII is a strict subset of UTF-8; we probe it last so that valid UTF-8
# files with non-ASCII characters are not rejected.
# ---------------------------------------------------------------------------
_SUPPORTED_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "ascii")


class SourceReaderError(Exception):
    """
    Raised when the Source Reader cannot read or decode a source file.

    Attributes:
        path: The :class:`~pathlib.Path` that caused the failure.
        message: Human-readable description of the failure.

    Examples:
        >>> raise SourceReaderError(Path("missing.cbl"), "File not found")
        Traceback (most recent call last):
            ...
        app.parser.lexer.source_reader.SourceReaderError: missing.cbl: File not found
    """

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


class SourceReader:
    """
    Read a COBOL source file from disk and return its contents as a string.

    The Source Reader is the first stage of the COBOL compiler pipeline.  It
    is responsible *only* for I/O and encoding detection.  It performs no
    lexical analysis, format detection, or source normalisation.

    Supported encodings (probed in order):
        - UTF-8 with BOM (``utf-8-sig``)
        - UTF-8 (``utf-8``)
        - ASCII (``ascii``)

    All other encodings (e.g. EBCDIC, Latin-1) raise
    :class:`SourceReaderError`.

    Examples:
        >>> from pathlib import Path
        >>> reader = SourceReader()
        >>> source = reader.read(Path("hello.cbl"))  # returns str
    """

    def read(self, path: Path) -> str:
        """
        Read *path* from disk and return its contents as a string.

        The source text is returned exactly as it appears in the file.
        No normalisation, stripping, or line-ending conversion is applied
        beyond what the Python codec performs (UTF-8 BOM stripping only).

        Args:
            path:
                Absolute or relative :class:`~pathlib.Path` to the COBOL
                source file.

        Returns:
            The full text of the source file as a :class:`str`.

        Raises:
            SourceReaderError:
                - If *path* does not exist or is not a regular file.
                - If the file's encoding is not one of the supported encodings.

        Examples:
            >>> reader = SourceReader()
            >>> source = reader.read(Path("payroll.cbl"))
            >>> isinstance(source, str)
            True
        """
        logger.debug("Reading source file: {}", path)

        if not path.exists():
            logger.error("Source file not found: {}", path)
            raise SourceReaderError(path, "File not found")

        if not path.is_file():
            logger.error("Path is not a regular file: {}", path)
            raise SourceReaderError(path, "Path is not a regular file")

        raw: bytes = path.read_bytes()

        for encoding in _SUPPORTED_ENCODINGS:
            try:
                source = codecs.decode(raw, encoding, errors="strict")
                logger.debug(
                    "Successfully decoded {} using encoding '{}'", path, encoding
                )
                return source  # type: ignore[return-value]
            except (UnicodeDecodeError, LookupError):
                continue

        logger.error("Unsupported encoding for file: {}", path)
        raise SourceReaderError(
            path,
            "Unsupported encoding. Supported encodings: UTF-8, UTF-8 BOM, ASCII.",
        )
