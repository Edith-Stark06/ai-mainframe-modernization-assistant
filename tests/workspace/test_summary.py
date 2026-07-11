"""
Summary Generator Tests.

Purpose:
    Verify that :class:`app.workspace.summary.SummaryGenerator` correctly
    derives aggregate statistics from a
    :class:`app.workspace.models.WorkspaceInventory`.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import UTC, datetime

import pytest

from app.workspace.models import (
    FileType,
    ScannedFile,
    TypeCount,
    WorkspaceInventory,
    WorkspaceSummary,
)
from app.workspace.summary import SummaryGenerator


@pytest.fixture()
def gen() -> SummaryGenerator:
    """Return a :class:`SummaryGenerator` instance."""
    return SummaryGenerator()


def _make_scanned_file(
    filename: str,
    file_type: FileType,
    size_bytes: int = 100,
) -> ScannedFile:
    """Construct a minimal :class:`ScannedFile` for use in tests."""
    return ScannedFile(
        path=f"/workspace/ws-test/{filename}",
        filename=filename,
        extension=filename[filename.rfind(".") :] if "." in filename else "",
        sha256="a" * 64,
        size_bytes=size_bytes,
        file_type=file_type,
    )


def _make_inventory(files: list[ScannedFile]) -> WorkspaceInventory:
    """Build a :class:`WorkspaceInventory` from *files*."""
    return WorkspaceInventory(
        workspace_id="ws-test-001",
        files=files,
        total_files=len(files),
    )


# ---------------------------------------------------------------------------
# Return type and basic structure
# ---------------------------------------------------------------------------


class TestSummaryGeneratorReturnType:
    """Tests for the return type and basic structure of generate()."""

    def test_generate_returns_workspace_summary(
        self, gen: SummaryGenerator
    ) -> None:
        """generate() must return a WorkspaceSummary instance."""
        inv = _make_inventory([])
        result = gen.generate(inv)
        assert isinstance(result, WorkspaceSummary)

    def test_workspace_id_preserved(self, gen: SummaryGenerator) -> None:
        """WorkspaceSummary.workspace_id must equal inventory.workspace_id."""
        inv = _make_inventory([])
        result = gen.generate(inv)
        assert result.workspace_id == inv.workspace_id

    def test_scanned_at_is_set(self, gen: SummaryGenerator) -> None:
        """WorkspaceSummary.scanned_at must be a non-None datetime."""
        inv = _make_inventory([])
        result = gen.generate(inv)
        assert result.scanned_at is not None


# ---------------------------------------------------------------------------
# Empty inventory
# ---------------------------------------------------------------------------


class TestSummaryGeneratorEmpty:
    """Tests for an empty inventory."""

    def test_empty_inventory_total_files_zero(self, gen: SummaryGenerator) -> None:
        """An empty inventory must produce total_files=0."""
        inv = _make_inventory([])
        result = gen.generate(inv)
        assert result.total_files == 0

    def test_empty_inventory_by_type_is_empty(self, gen: SummaryGenerator) -> None:
        """An empty inventory must produce an empty by_type list."""
        inv = _make_inventory([])
        result = gen.generate(inv)
        assert result.by_type == []

    def test_empty_inventory_total_size_is_zero(self, gen: SummaryGenerator) -> None:
        """An empty inventory must produce total_size_bytes=0."""
        inv = _make_inventory([])
        result = gen.generate(inv)
        assert result.total_size_bytes == 0


# ---------------------------------------------------------------------------
# Single file
# ---------------------------------------------------------------------------


class TestSummaryGeneratorSingleFile:
    """Tests for a single-file inventory."""

    def test_single_cobol_file_counted(self, gen: SummaryGenerator) -> None:
        """One COBOL file must produce a TypeCount of 1 for COBOL."""
        files = [_make_scanned_file("payroll.cbl", FileType.COBOL, size_bytes=512)]
        inv = _make_inventory(files)
        result = gen.generate(inv)
        assert result.total_files == 1
        cobol_counts = [tc for tc in result.by_type if tc.file_type == FileType.COBOL.value]
        assert len(cobol_counts) == 1
        assert cobol_counts[0].count == 1

    def test_single_file_total_size_correct(self, gen: SummaryGenerator) -> None:
        """total_size_bytes must equal the size of the single file."""
        files = [_make_scanned_file("prog.cbl", FileType.COBOL, size_bytes=1024)]
        inv = _make_inventory(files)
        result = gen.generate(inv)
        assert result.total_size_bytes == 1024


# ---------------------------------------------------------------------------
# Multiple files
# ---------------------------------------------------------------------------


class TestSummaryGeneratorMultipleFiles:
    """Tests for multi-file inventories."""

    def test_multiple_types_all_counted(self, gen: SummaryGenerator) -> None:
        """Files of different types must each produce a separate TypeCount."""
        files = [
            _make_scanned_file("a.cbl", FileType.COBOL),
            _make_scanned_file("b.cbl", FileType.COBOL),
            _make_scanned_file("c.cpy", FileType.COPYBOOK),
            _make_scanned_file("d.jcl", FileType.JCL),
        ]
        inv = _make_inventory(files)
        result = gen.generate(inv)

        by_type_map = {tc.file_type: tc.count for tc in result.by_type}
        assert by_type_map[FileType.COBOL.value] == 2
        assert by_type_map[FileType.COPYBOOK.value] == 1
        assert by_type_map[FileType.JCL.value] == 1

    def test_total_files_matches_inventory(self, gen: SummaryGenerator) -> None:
        """total_files must equal inventory.total_files."""
        files = [
            _make_scanned_file(f"file{i}.cbl", FileType.COBOL) for i in range(5)
        ]
        inv = _make_inventory(files)
        result = gen.generate(inv)
        assert result.total_files == 5

    def test_total_size_is_sum_of_all_files(self, gen: SummaryGenerator) -> None:
        """total_size_bytes must be the sum of all file sizes."""
        files = [
            _make_scanned_file("a.cbl", FileType.COBOL, size_bytes=100),
            _make_scanned_file("b.jcl", FileType.JCL, size_bytes=200),
            _make_scanned_file("c.cpy", FileType.COPYBOOK, size_bytes=50),
        ]
        inv = _make_inventory(files)
        result = gen.generate(inv)
        assert result.total_size_bytes == 350

    def test_by_type_sorted_descending_by_count(self, gen: SummaryGenerator) -> None:
        """by_type must be sorted by count in descending order."""
        files = [
            _make_scanned_file("a.cbl", FileType.COBOL),
            _make_scanned_file("b.cbl", FileType.COBOL),
            _make_scanned_file("c.cbl", FileType.COBOL),
            _make_scanned_file("d.jcl", FileType.JCL),
            _make_scanned_file("e.jcl", FileType.JCL),
            _make_scanned_file("f.cpy", FileType.COPYBOOK),
        ]
        inv = _make_inventory(files)
        result = gen.generate(inv)
        counts = [tc.count for tc in result.by_type]
        assert counts == sorted(counts, reverse=True)

    def test_by_type_only_contains_types_present(self, gen: SummaryGenerator) -> None:
        """by_type must not include zero-count entries."""
        files = [_make_scanned_file("prog.cbl", FileType.COBOL)]
        inv = _make_inventory(files)
        result = gen.generate(inv)
        # Should only have one entry (COBOL), not all 9 FileType values
        assert len(result.by_type) == 1

    def test_unknown_type_counted_in_summary(self, gen: SummaryGenerator) -> None:
        """Files classified as UNKNOWN must appear in the summary."""
        files = [_make_scanned_file("mystery.dat", FileType.UNKNOWN)]
        inv = _make_inventory(files)
        result = gen.generate(inv)
        unknown = [tc for tc in result.by_type if tc.file_type == FileType.UNKNOWN.value]
        assert len(unknown) == 1
        assert unknown[0].count == 1
