"""
Workspace Scanner.

Purpose:
    Recursively walk a workspace directory, discover all files, and
    produce a list of ``(path, content)`` pairs ready for classification
    and metadata extraction.

Responsibilities:
    - Recursively enumerate every regular file under the workspace root.
    - Support nested sub-directories (standard recursive walk).
    - Support ZIP archives: expand in-memory and yield each member as if
      it were a regular file, without writing to disk.
    - Compute the SHA-256 digest and size of each file as it is read.
    - Return a typed list of :class:`~app.workspace.models.ScannedFile`
      records (with classification delegated to ``FileClassifier``).
    - Never parse file content — only discover and read bytes.

Dependencies:
    - pathlib                  — :class:`pathlib.Path`
    - hashlib                  — SHA-256 computation
    - zipfile                  — ZIP archive extraction
    - app.workspace.classifier — :class:`FileClassifier`
    - app.workspace.models     — :class:`ScannedFile`
    - app.core.logging         — Loguru logger

Examples:
    Scanning a workspace directory::

        from pathlib import Path
        from app.workspace.scanner import WorkspaceScanner

        scanner = WorkspaceScanner()
        files = scanner.scan(Path("/workspace/ws-001"))
        for f in files:
            print(f.filename, f.file_type)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import hashlib
import io
import zipfile
from pathlib import Path

from app.core.logging import logger
from app.workspace.classifier import FileClassifier
from app.workspace.models import ScannedFile

__all__ = ["WorkspaceScanner"]

_classifier = FileClassifier()


class WorkspaceScanner:
    """
    Recursively scans a workspace directory and produces ``ScannedFile`` records.

    ZIP archives found during the scan are transparently expanded and their
    members treated as if they were regular files.  Nested ZIPs are not
    recursively expanded.

    Attributes:
        _classifier: Shared :class:`FileClassifier` instance.
    """

    def __init__(self) -> None:
        """Initialise the scanner with its collaborators."""
        self._classifier = FileClassifier()

    def scan(self, workspace_path: Path) -> list[ScannedFile]:
        """
        Recursively scan *workspace_path* and return all discovered files.

        Args:
            workspace_path: Absolute :class:`pathlib.Path` to the workspace
                            directory to scan.

        Returns:
            Ordered list of :class:`~app.workspace.models.ScannedFile`
            records, one per discovered file.  ZIP archive members are
            included as individual records.

        Raises:
            FileNotFoundError: If *workspace_path* does not exist.
            NotADirectoryError: If *workspace_path* is not a directory.
        """
        if not workspace_path.exists():
            raise FileNotFoundError(
                f"Workspace path does not exist: {workspace_path}"
            )
        if not workspace_path.is_dir():
            raise NotADirectoryError(
                f"Workspace path is not a directory: {workspace_path}"
            )

        logger.info(
            "WorkspaceScanner: scanning '{}' …", workspace_path
        )

        scanned: list[ScannedFile] = []
        for file_path in sorted(workspace_path.rglob("*")):
            if not file_path.is_file():
                continue

            ext = self._extension(file_path.name)
            if ext == ".zip":
                records = self._scan_zip(file_path, workspace_path)
                scanned.extend(records)
            else:
                record = self._scan_file(file_path, workspace_path)
                scanned.append(record)

        logger.info(
            "WorkspaceScanner: discovered {} file(s) in '{}'.",
            len(scanned),
            workspace_path,
        )
        return scanned

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _scan_file(
        self,
        file_path: Path,
        workspace_root: Path,
    ) -> ScannedFile:
        """
        Read *file_path* and build a :class:`ScannedFile` record.

        Args:
            file_path:       Absolute path to the file.
            workspace_root:  Root of the workspace (used for relative path
                             computation in log messages).

        Returns:
            A populated :class:`~app.workspace.models.ScannedFile`.
        """
        content = file_path.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        file_type = self._classifier.classify(file_path.name, content)

        record = ScannedFile(
            path=str(file_path.resolve()),
            filename=file_path.name,
            extension=self._extension(file_path.name),
            sha256=sha256,
            size_bytes=len(content),
            file_type=file_type,
        )
        logger.debug(
            "WorkspaceScanner: scanned '{}' — type={}, size={} bytes.",
            file_path.name,
            file_type.value,
            len(content),
        )
        return record

    def _scan_zip(
        self,
        zip_path: Path,
        workspace_root: Path,
    ) -> list[ScannedFile]:
        """
        Expand a ZIP archive and build a :class:`ScannedFile` per member.

        Only members that are regular files (not directory entries) are
        processed.  Nested ZIP files inside the archive are not recursively
        expanded.

        Args:
            zip_path:       Absolute path to the ZIP file.
            workspace_root: Root of the workspace directory.

        Returns:
            List of :class:`~app.workspace.models.ScannedFile` records,
            one per extracted member.
        """
        records: list[ScannedFile] = []

        try:
            with zipfile.ZipFile(io.BytesIO(zip_path.read_bytes())) as zf:
                for member_name in zf.namelist():
                    if member_name.endswith("/"):
                        continue  # skip directory entries

                    member_content = zf.read(member_name)
                    basename = Path(member_name).name
                    sha256 = hashlib.sha256(member_content).hexdigest()
                    file_type = self._classifier.classify(basename, member_content)

                    record = ScannedFile(
                        path=f"{zip_path.resolve()}!/{member_name}",
                        filename=basename,
                        extension=self._extension(basename),
                        sha256=sha256,
                        size_bytes=len(member_content),
                        file_type=file_type,
                    )
                    records.append(record)
                    logger.debug(
                        "WorkspaceScanner: ZIP member '{}' — type={}, size={} bytes.",
                        member_name,
                        file_type.value,
                        len(member_content),
                    )
        except zipfile.BadZipFile:
            logger.warning(
                "WorkspaceScanner: '{}' is not a valid ZIP archive; skipping.",
                zip_path,
            )

        return records

    @staticmethod
    def _extension(filename: str) -> str:
        """
        Extract the lowercase dot-prefixed extension from *filename*.

        Args:
            filename: A filename string.

        Returns:
            Lowercase extension string, or ``""`` when absent.
        """
        idx = filename.rfind(".")
        if idx == -1 or idx == len(filename) - 1:
            return ""
        return filename[idx:].lower()
