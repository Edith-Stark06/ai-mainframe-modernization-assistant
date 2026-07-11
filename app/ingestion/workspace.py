"""
Workspace Manager.

Purpose:
    Manage the lifecycle of on-disk workspace directories that isolate
    each upload session's files from other sessions.

Responsibilities:
    - Create a uniquely named workspace directory under the configured
      root workspace directory.
    - Return a :class:`app.ingestion.models.WorkspaceRecord` describing
      the created workspace.
    - Delete a workspace directory and all its contents when requested.
    - Retrieve workspace metadata by workspace ID.
    - Never raise on benign conditions (e.g. workspace already gone on
      delete); log and return gracefully instead.

Dependencies:
    - pathlib               — :class:`pathlib.Path` for filesystem operations
    - uuid                  — UUID4 generation
    - app.core.config       — ``settings.workspace_dir``
    - app.core.exceptions   — :class:`ResourceNotFoundException`
    - app.core.logging      — Loguru logger
    - app.ingestion.models  — :class:`WorkspaceRecord`

Examples:
    Creating and deleting a workspace::

        from app.ingestion.workspace import WorkspaceManager

        mgr = WorkspaceManager()
        record = mgr.create()
        print(record.workspace_id)  # UUID4 string
        mgr.delete(record.workspace_id)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import shutil
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import ResourceNotFoundException
from app.core.logging import logger
from app.ingestion.models import WorkspaceRecord

__all__ = ["WorkspaceManager"]


class WorkspaceManager:
    """
    Manages the creation, retrieval, and deletion of workspace directories.

    Each workspace is a sub-directory of the configured workspace root
    whose name equals the workspace UUID.

    Attributes:
        _root: :class:`pathlib.Path` to the top-level workspace directory.
    """

    def __init__(self) -> None:
        """
        Initialise the manager and ensure the workspace root exists.

        The root directory is derived from ``settings.workspace_dir`` and
        is created if it does not already exist.
        """
        self._root = Path(settings.workspace_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        logger.debug("WorkspaceManager: root directory is '{}'.", self._root.resolve())

    def create(self) -> WorkspaceRecord:
        """
        Create a new workspace directory and return its record.

        A UUID4 is generated to name the directory, guaranteeing
        uniqueness across concurrent upload sessions.

        Returns:
            A :class:`~app.ingestion.models.WorkspaceRecord` with the
            workspace ID, absolute path, and creation timestamp.

        Raises:
            OSError: If the directory cannot be created (e.g. permissions).
        """
        workspace_id = str(uuid.uuid4())
        workspace_path = self._root / workspace_id
        workspace_path.mkdir(parents=True, exist_ok=False)

        record = WorkspaceRecord(
            workspace_id=workspace_id,
            path=str(workspace_path.resolve()),
        )

        logger.info(
            "WorkspaceManager: created workspace '{}' at '{}'.",
            workspace_id,
            record.path,
        )
        return record

    def get(self, workspace_id: str) -> WorkspaceRecord:
        """
        Retrieve metadata for an existing workspace.

        Args:
            workspace_id: UUID4 string identifying the workspace.

        Returns:
            A :class:`~app.ingestion.models.WorkspaceRecord` for the
            requested workspace.

        Raises:
            ResourceNotFoundException: If no workspace with the given ID
                exists on disk.
        """
        workspace_path = self._root / workspace_id
        if not workspace_path.is_dir():
            logger.warning("WorkspaceManager: workspace '{}' not found.", workspace_id)
            raise ResourceNotFoundException(
                resource="workspace",
                identifier=workspace_id,
            )

        return WorkspaceRecord(
            workspace_id=workspace_id,
            path=str(workspace_path.resolve()),
        )

    def delete(self, workspace_id: str) -> bool:
        """
        Delete a workspace directory and all its contents.

        Args:
            workspace_id: UUID4 string identifying the workspace to remove.

        Returns:
            ``True`` if the workspace was found and deleted, ``False`` if
            it did not exist (idempotent — not treated as an error).
        """
        workspace_path = self._root / workspace_id
        if not workspace_path.exists():
            logger.debug(
                "WorkspaceManager: workspace '{}' does not exist; "
                "nothing to delete.",
                workspace_id,
            )
            return False

        shutil.rmtree(workspace_path, ignore_errors=True)
        logger.info("WorkspaceManager: deleted workspace '{}'.", workspace_id)
        return True

    def workspace_path(self, workspace_id: str) -> Path:
        """
        Return the :class:`pathlib.Path` for *workspace_id* without validating existence.

        Args:
            workspace_id: UUID4 string identifying the workspace.

        Returns:
            The resolved :class:`pathlib.Path` of the workspace directory.
        """
        return (self._root / workspace_id).resolve()
