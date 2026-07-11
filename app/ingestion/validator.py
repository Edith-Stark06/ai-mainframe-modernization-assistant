"""
File Upload Validator.

Purpose:
    Enforce all pre-ingestion validation rules on uploaded files before
    any bytes are written to disk.

Responsibilities:
    - Validate file extension against the supported set.
    - Validate that the file is not empty (zero bytes).
    - Validate that the file does not exceed the configured size limit.
    - Validate that no duplicate filenames exist within a single request.
    - Raise typed :class:`app.core.exceptions.ValidationException`
      instances so the global exception handler surfaces clean 422
      responses to clients.

Dependencies:
    - app.core.config     — application settings (``max_upload_mb``)
    - app.core.exceptions — :class:`ValidationException`
    - app.core.logging    — Loguru logger

Examples:
    Validating a batch of files::

        from app.ingestion.validator import FileValidator

        validator = FileValidator()
        validator.validate_extension("payroll.cbl")
        validator.validate_size(b"...", filename="payroll.cbl")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.core.config import settings
from app.core.exceptions import ValidationException
from app.core.logging import logger

__all__ = ["FileValidator"]

# ---------------------------------------------------------------------------
# Supported extensions
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".cbl", ".cob", ".cpy", ".jcl", ".txt", ".zip"}
)


class FileValidator:
    """
    Stateless validator for uploaded mainframe files.

    All validation methods raise :class:`ValidationException` on failure
    so callers do not need to inspect return values; a clean return
    implies the check passed.
    """

    def validate_extension(self, filename: str) -> None:
        """
        Validate that *filename* carries a supported extension.

        Args:
            filename: The original filename supplied by the client
                      (e.g. ``"payroll.cbl"``).

        Raises:
            ValidationException: If the extension is absent or not in
                :data:`SUPPORTED_EXTENSIONS`.

        Examples:
            >>> validator = FileValidator()
            >>> validator.validate_extension("payroll.cbl")  # passes silently
            >>> validator.validate_extension("report.docx")  # raises
        """
        ext = self._extract_extension(filename)
        if ext not in SUPPORTED_EXTENSIONS:
            logger.warning(
                "FileValidator: unsupported extension '{}' in file '{}'.",
                ext or "<none>",
                filename,
            )
            raise ValidationException(
                message=(
                    f"File '{filename}' has an unsupported extension '{ext}'. "
                    f"Allowed: {sorted(SUPPORTED_EXTENSIONS)}."
                ),
                details={
                    "filename": filename,
                    "extension": ext,
                    "allowed": sorted(SUPPORTED_EXTENSIONS),
                },
            )
        logger.debug("FileValidator: extension '{}' accepted for '{}'.", ext, filename)

    def validate_not_empty(self, content: bytes, filename: str) -> None:
        """
        Validate that *content* is not an empty byte string.

        Args:
            content:  Raw file bytes.
            filename: Original filename (used in error messages).

        Raises:
            ValidationException: If ``len(content) == 0``.
        """
        if len(content) == 0:
            logger.warning("FileValidator: file '{}' is empty.", filename)
            raise ValidationException(
                message=f"File '{filename}' is empty. Empty files are not accepted.",
                details={"filename": filename, "size_bytes": 0},
            )
        logger.debug(
            "FileValidator: file '{}' is non-empty ({} bytes).",
            filename,
            len(content),
        )

    def validate_size(self, content: bytes, filename: str) -> None:
        """
        Validate that *content* does not exceed the configured size limit.

        The limit is read from ``settings.max_upload_mb``.

        Args:
            content:  Raw file bytes.
            filename: Original filename (used in error messages).

        Raises:
            ValidationException: If the content size exceeds the limit.
        """
        max_bytes = settings.max_upload_mb * 1024 * 1024
        size = len(content)
        if size > max_bytes:
            logger.warning(
                "FileValidator: file '{}' is {} bytes, exceeds {} MB limit.",
                filename,
                size,
                settings.max_upload_mb,
            )
            raise ValidationException(
                message=(
                    f"File '{filename}' is {size:,} bytes "
                    f"({size / 1_048_576:.2f} MB), which exceeds the "
                    f"{settings.max_upload_mb} MB upload limit."
                ),
                details={
                    "filename": filename,
                    "size_bytes": size,
                    "max_bytes": max_bytes,
                    "max_mb": settings.max_upload_mb,
                },
            )
        logger.debug(
            "FileValidator: size check passed for '{}' ({} bytes).",
            filename,
            size,
        )

    def validate_no_duplicates(self, filenames: list[str]) -> None:
        """
        Validate that no two files in *filenames* share the same name.

        Args:
            filenames: Ordered list of filenames from the upload request.

        Raises:
            ValidationException: If one or more duplicate filenames are
                detected.
        """
        seen: set[str] = set()
        duplicates: list[str] = []
        for name in filenames:
            lower = name.lower()
            if lower in seen:
                duplicates.append(name)
            seen.add(lower)

        if duplicates:
            logger.warning(
                "FileValidator: duplicate filenames detected: {}.", duplicates
            )
            raise ValidationException(
                message=(
                    f"Duplicate filename(s) detected: {duplicates}. "
                    "Each filename must be unique within a single upload request."
                ),
                details={"duplicates": duplicates},
            )
        logger.debug(
            "FileValidator: no duplicate filenames in {} files.", len(filenames)
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_extension(filename: str) -> str:
        """
        Extract the lowercase extension (including the dot) from *filename*.

        Args:
            filename: Full filename string.

        Returns:
            Lowercase extension string, or ``""`` if none is present.
        """
        idx = filename.rfind(".")
        if idx == -1 or idx == len(filename) - 1:
            return ""
        return filename[idx:].lower()
