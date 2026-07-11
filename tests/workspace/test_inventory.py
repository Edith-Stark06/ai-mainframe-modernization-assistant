"""
Inventory Builder Tests.

Purpose:
    Verify that :class:`app.workspace.inventory.InventoryBuilder` correctly
    assembles a :class:`app.workspace.models.WorkspaceInventory` from a
    scanned workspace directory.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from pathlib import Path

import pytest

from app.core.exceptions import ResourceNotFoundException
from app.workspace.inventory import InventoryBuilder
from app.workspace.models import WorkspaceInventory


@pytest.fixture()
def builder() -> InventoryBuilder:
    """Return an :class:`InventoryBuilder` instance."""
    return InventoryBuilder()


_WS_ID = "test-workspace-ws-001"

_COBOL = b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TEST.\n"
_JCL = b"//MYJOB   JOB (ACCT),'TEST',CLASS=A\n"


# ---------------------------------------------------------------------------
# Nominal builds
# ---------------------------------------------------------------------------


class TestInventoryBuilderNominal:
    """Tests for successful inventory builds."""

    def test_build_returns_workspace_inventory(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """build() must return a WorkspaceInventory instance."""
        (tmp_path / "prog.cbl").write_bytes(_COBOL)
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert isinstance(result, WorkspaceInventory)

    def test_build_workspace_id_preserved(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """WorkspaceInventory.workspace_id must match the supplied ID."""
        (tmp_path / "prog.cbl").write_bytes(_COBOL)
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert result.workspace_id == _WS_ID

    def test_build_empty_workspace_has_zero_total(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """An empty workspace must produce an inventory with total_files=0."""
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert result.total_files == 0
        assert result.files == []

    def test_build_total_files_matches_actual_count(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """total_files must equal the number of ScannedFile records."""
        (tmp_path / "a.cbl").write_bytes(_COBOL)
        (tmp_path / "b.jcl").write_bytes(_JCL)
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert result.total_files == 2
        assert len(result.files) == 2

    def test_build_files_list_contains_correct_filenames(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """Each ScannedFile in the inventory must carry the correct filename."""
        (tmp_path / "payroll.cbl").write_bytes(_COBOL)
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert result.files[0].filename == "payroll.cbl"

    def test_build_scanned_at_is_set(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """WorkspaceInventory.scanned_at must be a non-None datetime."""
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert result.scanned_at is not None

    def test_build_nested_files_included(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """Files in sub-directories must be included in the inventory."""
        sub = tmp_path / "programs"
        sub.mkdir()
        (sub / "report.cbl").write_bytes(_COBOL)
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert result.total_files == 1
        assert result.files[0].filename == "report.cbl"

    def test_build_multiple_types_in_inventory(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """Inventory must contain files of different types."""
        (tmp_path / "prog.cbl").write_bytes(_COBOL)
        (tmp_path / "copy.cpy").write_bytes(b"01 REC.\n")
        (tmp_path / "job.jcl").write_bytes(_JCL)
        result = builder.build(workspace_id=_WS_ID, path=tmp_path)
        assert result.total_files == 3


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestInventoryBuilderErrors:
    """Tests for error conditions in InventoryBuilder."""

    def test_build_raises_for_missing_workspace(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """build() must raise ResourceNotFoundException for a non-existent path."""
        missing = tmp_path / "does-not-exist"
        with pytest.raises(ResourceNotFoundException) as exc_info:
            builder.build(workspace_id="ghost-ws", path=missing)
        assert exc_info.value.status_code == 404

    def test_build_raises_for_file_path(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """build() must raise ResourceNotFoundException when path is a file, not a dir."""
        f = tmp_path / "file.txt"
        f.write_bytes(b"data")
        with pytest.raises(ResourceNotFoundException):
            builder.build(workspace_id="ws-file", path=f)

    def test_resource_not_found_contains_workspace_id(
        self, builder: InventoryBuilder, tmp_path: Path
    ) -> None:
        """ResourceNotFoundException message must reference the workspace identifier."""
        missing = tmp_path / "ghost"
        with pytest.raises(ResourceNotFoundException) as exc_info:
            builder.build(workspace_id="ghost-ws-123", path=missing)
        # The exception message must mention the workspace ID
        assert "ghost-ws-123" in str(exc_info.value)
