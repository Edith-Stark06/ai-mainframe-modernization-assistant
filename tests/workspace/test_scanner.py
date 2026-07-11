"""
Workspace Scanner Tests.

Purpose:
    Verify that :class:`app.workspace.scanner.WorkspaceScanner` correctly
    discovers regular files, handles nested directories, transparently
    expands ZIP archives, and raises on invalid paths.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import io
import zipfile
from pathlib import Path

import pytest

from app.workspace.models import FileType, ScannedFile
from app.workspace.scanner import WorkspaceScanner


@pytest.fixture()
def scanner() -> WorkspaceScanner:
    """Return a :class:`WorkspaceScanner` instance."""
    return WorkspaceScanner()


# ---------------------------------------------------------------------------
# Basic scanning
# ---------------------------------------------------------------------------


class TestWorkspaceScannerBasic:
    """Tests for basic directory scanning behaviour."""

    def test_scan_empty_workspace_returns_empty_list(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """Scanning an empty directory must return an empty list."""
        result = scanner.scan(tmp_path)
        assert result == []

    def test_scan_returns_list_of_scanned_files(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """scan() must return a list of ScannedFile instances."""
        (tmp_path / "prog.cbl").write_bytes(b"IDENTIFICATION DIVISION.\n")
        result = scanner.scan(tmp_path)
        assert all(isinstance(f, ScannedFile) for f in result)

    def test_scan_discovers_single_file(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """A directory with one file must produce exactly one record."""
        (tmp_path / "payroll.cbl").write_bytes(b"ID DIVISION.\n")
        result = scanner.scan(tmp_path)
        assert len(result) == 1

    def test_scan_filename_correct(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ScannedFile.filename must match the written file name."""
        (tmp_path / "payroll.cbl").write_bytes(b"data")
        result = scanner.scan(tmp_path)
        assert result[0].filename == "payroll.cbl"

    def test_scan_extension_correct(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ScannedFile.extension must be the lowercase dot-extension."""
        (tmp_path / "batch.jcl").write_bytes(b"//JOB\n")
        result = scanner.scan(tmp_path)
        assert result[0].extension == ".jcl"

    def test_scan_size_bytes_correct(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ScannedFile.size_bytes must equal len(file_content)."""
        content = b"IDENTIFICATION DIVISION.\n"
        (tmp_path / "prog.cbl").write_bytes(content)
        result = scanner.scan(tmp_path)
        assert result[0].size_bytes == len(content)

    def test_scan_sha256_is_64_chars(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ScannedFile.sha256 must be a 64-character hex string."""
        (tmp_path / "prog.cbl").write_bytes(b"data")
        result = scanner.scan(tmp_path)
        assert len(result[0].sha256) == 64

    def test_scan_sha256_correctness(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """SHA-256 digest must match the hashlib reference value."""
        import hashlib

        content = b"IDENTIFICATION DIVISION.\n"
        (tmp_path / "prog.cbl").write_bytes(content)
        result = scanner.scan(tmp_path)
        expected = hashlib.sha256(content).hexdigest()
        assert result[0].sha256 == expected

    def test_scan_file_type_assigned(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ScannedFile.file_type must be assigned a FileType value."""
        (tmp_path / "prog.cbl").write_bytes(b"data")
        result = scanner.scan(tmp_path)
        assert result[0].file_type == FileType.COBOL.value

    def test_scan_multiple_files(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """Scanning a directory with multiple files must return all of them."""
        (tmp_path / "a.cbl").write_bytes(b"data1")
        (tmp_path / "b.jcl").write_bytes(b"//JOB\n")
        (tmp_path / "c.cpy").write_bytes(b"01 REC.\n")
        result = scanner.scan(tmp_path)
        assert len(result) == 3

    def test_scan_path_field_is_absolute(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ScannedFile.path must be an absolute path string."""
        (tmp_path / "prog.cbl").write_bytes(b"data")
        result = scanner.scan(tmp_path)
        assert Path(result[0].path).is_absolute()


# ---------------------------------------------------------------------------
# Nested directory scanning
# ---------------------------------------------------------------------------


class TestWorkspaceScannerNested:
    """Tests for recursive sub-directory discovery."""

    def test_scan_discovers_files_in_subdirectory(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """Files in sub-directories must be discovered recursively."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "prog.cbl").write_bytes(b"data")
        result = scanner.scan(tmp_path)
        assert len(result) == 1
        assert result[0].filename == "prog.cbl"

    def test_scan_discovers_files_in_deeply_nested_directory(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """Files in deeply nested directories must be discovered."""
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.cbl").write_bytes(b"data")
        result = scanner.scan(tmp_path)
        assert any(f.filename == "deep.cbl" for f in result)

    def test_scan_root_and_subdirectory_files_combined(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """Files at root and in subdirectories must all appear in result."""
        (tmp_path / "root.cbl").write_bytes(b"data")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "sub.jcl").write_bytes(b"//JOB\n")
        result = scanner.scan(tmp_path)
        filenames = {f.filename for f in result}
        assert "root.cbl" in filenames
        assert "sub.jcl" in filenames


# ---------------------------------------------------------------------------
# ZIP expansion
# ---------------------------------------------------------------------------


class TestWorkspaceScannerZip:
    """Tests for ZIP archive transparent expansion."""

    def _make_zip(self, files: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in files.items():
                zf.writestr(name, data)
        return buf.getvalue()

    def test_zip_members_included_in_scan(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ZIP archive members must be included as individual ScannedFile records."""
        zip_bytes = self._make_zip({"archived.cbl": b"data", "batch.jcl": b"//JOB\n"})
        (tmp_path / "bundle.zip").write_bytes(zip_bytes)
        result = scanner.scan(tmp_path)
        filenames = {f.filename for f in result}
        assert "archived.cbl" in filenames
        assert "batch.jcl" in filenames

    def test_zip_member_type_classified(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """ZIP archive members must be classified by their own extension."""
        zip_bytes = self._make_zip({"prog.cbl": b"data"})
        (tmp_path / "arch.zip").write_bytes(zip_bytes)
        result = scanner.scan(tmp_path)
        cbl_records = [f for f in result if f.filename == "prog.cbl"]
        assert len(cbl_records) == 1
        assert cbl_records[0].file_type == FileType.COBOL.value

    def test_invalid_zip_does_not_raise(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """A corrupt ZIP file must be skipped without raising an exception."""
        (tmp_path / "bad.zip").write_bytes(b"this is not a zip")
        # Must not raise
        result = scanner.scan(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestWorkspaceScannerErrors:
    """Tests for error conditions."""

    def test_scan_nonexistent_path_raises(self, scanner: WorkspaceScanner) -> None:
        """Scanning a non-existent path must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            scanner.scan(Path("/nonexistent/path/that/does/not/exist"))

    def test_scan_file_path_raises(
        self, scanner: WorkspaceScanner, tmp_path: Path
    ) -> None:
        """Passing a file path instead of a directory must raise NotADirectoryError."""
        f = tmp_path / "file.cbl"
        f.write_bytes(b"data")
        with pytest.raises(NotADirectoryError):
            scanner.scan(f)
