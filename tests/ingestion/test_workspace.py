"""
Workspace Manager Tests.

Purpose:
    Verify the lifecycle operations of :class:`app.ingestion.workspace.WorkspaceManager`:
    workspace creation, retrieval, deletion, and path helpers.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from pathlib import Path

import pytest

from app.core.exceptions import ResourceNotFoundException
from app.ingestion.models import WorkspaceRecord
from app.ingestion.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Helper: build an isolated WorkspaceManager for each test
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path: Path) -> WorkspaceManager:
    """Return a :class:`WorkspaceManager` rooted at *tmp_path*."""
    mgr = WorkspaceManager.__new__(WorkspaceManager)
    mgr._root = tmp_path  # type: ignore[attr-defined]
    tmp_path.mkdir(parents=True, exist_ok=True)
    return mgr


# ---------------------------------------------------------------------------
# Creation tests
# ---------------------------------------------------------------------------


class TestWorkspaceManagerCreate:
    """Tests for :meth:`WorkspaceManager.create`."""

    def test_create_returns_workspace_record(self, manager: WorkspaceManager) -> None:
        """create() must return a WorkspaceRecord instance."""
        record = manager.create()
        assert isinstance(record, WorkspaceRecord)

    def test_create_returns_unique_ids(self, manager: WorkspaceManager) -> None:
        """Successive create() calls must return different workspace IDs."""
        r1 = manager.create()
        r2 = manager.create()
        assert r1.workspace_id != r2.workspace_id

    def test_create_directory_exists_on_disk(self, manager: WorkspaceManager) -> None:
        """The workspace directory must be created on the filesystem."""
        record = manager.create()
        assert Path(record.path).is_dir()

    def test_create_workspace_id_is_uuid(self, manager: WorkspaceManager) -> None:
        """workspace_id must be a valid UUID4 string."""
        import uuid

        record = manager.create()
        parsed = uuid.UUID(record.workspace_id, version=4)
        assert str(parsed) == record.workspace_id

    def test_create_path_is_under_root(
        self, manager: WorkspaceManager, tmp_path: Path
    ) -> None:
        """The created workspace path must be a child of the root directory."""
        record = manager.create()
        assert Path(record.path).parent.resolve() == tmp_path.resolve()

    def test_create_sets_created_at(self, manager: WorkspaceManager) -> None:
        """WorkspaceRecord must carry a non-None created_at timestamp."""
        record = manager.create()
        assert record.created_at is not None


# ---------------------------------------------------------------------------
# Retrieval tests
# ---------------------------------------------------------------------------


class TestWorkspaceManagerGet:
    """Tests for :meth:`WorkspaceManager.get`."""

    def test_get_returns_existing_workspace(self, manager: WorkspaceManager) -> None:
        """get() must return the WorkspaceRecord for an existing workspace."""
        record = manager.create()
        retrieved = manager.get(record.workspace_id)
        assert retrieved.workspace_id == record.workspace_id

    def test_get_raises_for_nonexistent_workspace(
        self, manager: WorkspaceManager
    ) -> None:
        """get() must raise ResourceNotFoundException for unknown IDs."""
        with pytest.raises(ResourceNotFoundException):
            manager.get("does-not-exist-uuid")

    def test_get_path_matches_create(self, manager: WorkspaceManager) -> None:
        """The path returned by get() must match the path from create()."""
        record = manager.create()
        retrieved = manager.get(record.workspace_id)
        assert retrieved.path == record.path


# ---------------------------------------------------------------------------
# Deletion tests
# ---------------------------------------------------------------------------


class TestWorkspaceManagerDelete:
    """Tests for :meth:`WorkspaceManager.delete`."""

    def test_delete_returns_true_for_existing_workspace(
        self, manager: WorkspaceManager
    ) -> None:
        """delete() must return True when the workspace existed."""
        record = manager.create()
        assert manager.delete(record.workspace_id) is True

    def test_delete_removes_directory(self, manager: WorkspaceManager) -> None:
        """The workspace directory must be gone after delete()."""
        record = manager.create()
        manager.delete(record.workspace_id)
        assert not Path(record.path).exists()

    def test_delete_returns_false_for_nonexistent_workspace(
        self, manager: WorkspaceManager
    ) -> None:
        """delete() must return False (not raise) for unknown IDs."""
        assert manager.delete("ghost-workspace") is False

    def test_delete_is_idempotent(self, manager: WorkspaceManager) -> None:
        """Calling delete() twice on the same ID must not raise."""
        record = manager.create()
        manager.delete(record.workspace_id)
        # Second call — must not raise
        result = manager.delete(record.workspace_id)
        assert result is False


# ---------------------------------------------------------------------------
# Path helper tests
# ---------------------------------------------------------------------------


class TestWorkspaceManagerPath:
    """Tests for :meth:`WorkspaceManager.workspace_path`."""

    def test_workspace_path_returns_path_object(
        self, manager: WorkspaceManager
    ) -> None:
        """workspace_path() must return a pathlib.Path."""
        record = manager.create()
        p = manager.workspace_path(record.workspace_id)
        assert isinstance(p, Path)

    def test_workspace_path_ends_with_workspace_id(
        self, manager: WorkspaceManager
    ) -> None:
        """The path must end with the workspace ID as its final component."""
        record = manager.create()
        p = manager.workspace_path(record.workspace_id)
        assert p.name == record.workspace_id
