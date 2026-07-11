"""
File Uploader.

Purpose:
    Persist validated file bytes to the workspace directory on disk,
    handling both regular mainframe files and ZIP archives.

Responsibilities:
    - Write individual files (COBOL, JCL, Copybook, plain text) to the
      workspace directory.
    - Expand ZIP archives and write each member that has a supported
      extension to the workspace directory.
    - Skip ZIP members with unsupported extensions and log the skipped
      names.
    - Return the list of ``(filename, content)`` pairs that were actually
      written, enabling the service layer to extract metadata for each.
    - Never parse file content — only ingest.

Dependencies:
    - pathlib               — :class:`pathlib.Path` for filesystem writes
    - zipfile               — ZIP extraction
    - app.core.logging      — Loguru logger
    - app.ingestion.validator — :data:`SUPPORTED_EXTENSIONS` constant

Examples:
    Writing a single file to a workspace::

        from app.ingestion.uploader import FileUploader

        uploader = FileUploader()
        saved = uploader.save_file(
            workspace_path=Path("/workspace/ws-uuid"),
            filename="payroll.cbl",
            content=b"IDENTIFICATION DIVISION.",
        )

    Expanding a ZIP archive::

        with open("batch.zip", "rb") as f:
            saved_files = uploader.expand_zip(
                workspace_path=Path("/workspace/ws-uuid"),
                zip_content=f.read(),
            )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import io
import zipfile
from pathlib import Path

from app.core.logging import logger
from app.ingestion.validator import SUPPORTED_EXTENSIONS

__all__ = ["FileUploader"]

# Exclude ZIP from the set expanded from nested archives to avoid recursive
# expansion of arbitrarily nested archives.
_EXPANDABLE_EXTENSIONS: frozenset[str] = SUPPORTED_EXTENSIONS - frozenset({".zip"})


class FileUploader:
    """
    Persists validated file bytes to workspace directories on disk.

    All write operations are synchronous.  The service layer is
    responsible for calling this from within an executor if async I/O
    is required.
    """

    def save_file(
        self,
        workspace_path: Path,
        filename: str,
        content: bytes,
    ) -> tuple[str, bytes]:
        """
        Write *content* to *workspace_path* / *filename* and return it.

        Args:
            workspace_path: Absolute :class:`pathlib.Path` to the workspace
                            directory.
            filename:       Original filename to use on disk.
            content:        Validated raw bytes to write.

        Returns:
            A ``(filename, content)`` tuple confirming what was saved.

        Raises:
            OSError: If the file cannot be written (e.g. permissions,
                     full disk).
        """
        dest = workspace_path / filename
        dest.write_bytes(content)
        logger.info(
            "FileUploader: saved '{}' ({} bytes) to '{}'.",
            filename,
            len(content),
            dest,
        )
        return filename, content

    def expand_zip(
        self,
        workspace_path: Path,
        zip_content: bytes,
    ) -> list[tuple[str, bytes]]:
        """
        Extract members with supported extensions from a ZIP archive.

        Members whose extensions are not in :data:`_EXPANDABLE_EXTENSIONS`
        are skipped and logged.  Nested ZIP files inside the archive are
        also skipped (no recursive expansion).

        Args:
            workspace_path: Absolute :class:`pathlib.Path` to the workspace
                            directory.
            zip_content:    Raw bytes of the ZIP archive.

        Returns:
            Ordered list of ``(filename, content)`` tuples for every member
            that was successfully extracted and written.

        Raises:
            zipfile.BadZipFile: If *zip_content* is not a valid ZIP archive.
        """
        saved: list[tuple[str, bytes]] = []

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            members = zf.namelist()
            logger.info(
                "FileUploader: ZIP archive contains {} member(s).", len(members)
            )

            for member_name in members:
                # Skip directories stored as entries
                if member_name.endswith("/"):
                    continue

                # Extract just the basename (ignore directory hierarchy
                # inside the ZIP so that all files land in workspace root)
                basename = Path(member_name).name
                ext = _extract_extension(basename)

                if ext not in _EXPANDABLE_EXTENSIONS:
                    logger.debug(
                        "FileUploader: skipping ZIP member '{}' "
                        "(unsupported extension '{}').",
                        member_name,
                        ext or "<none>",
                    )
                    continue

                member_content = zf.read(member_name)
                self.save_file(workspace_path, basename, member_content)
                saved.append((basename, member_content))

        logger.info(
            "FileUploader: extracted {} supported file(s) from ZIP.",
            len(saved),
        )
        return saved


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _extract_extension(filename: str) -> str:
    """
    Return the lowercase extension (including dot) of *filename*.

    Args:
        filename: A filename string.

    Returns:
        Lowercase extension string, or ``""`` when none is present.
    """
    idx = filename.rfind(".")
    if idx == -1 or idx == len(filename) - 1:
        return ""
    return filename[idx:].lower()
