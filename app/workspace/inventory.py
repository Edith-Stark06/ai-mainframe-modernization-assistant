"""
Workspace Inventory Builder.

Purpose:
    Orchestrate a full workspace scan and assemble a
    :class:`~app.workspace.models.WorkspaceInventory` from the discovered
    :class:`~app.workspace.models.ScannedFile` records.

Responsibilities:
    - Accept a workspace directory path.
    - Delegate file discovery to :class:`app.workspace.scanner.WorkspaceScanner`.
    - Assemble and return a :class:`WorkspaceInventory` containing all
      discovered files and aggregate totals.
    - Raise :class:`app.core.exceptions.ResourceNotFoundException` when
      the workspace directory does not exist.

Dependencies:
    - pathlib                  — :class:`pathlib.Path`
    - app.core.exceptions      — :class:`ResourceNotFoundException`
    - app.core.logging         — Loguru logger
    - app.workspace.models     — :class:`WorkspaceInventory`
    - app.workspace.scanner    — :class:`WorkspaceScanner`

Examples:
    Building an inventory::

        from pathlib import Path
        from app.workspace.inventory import InventoryBuilder

        builder = InventoryBuilder()
        inv = builder.build(workspace_id="ws-001", path=Path("/workspace/ws-001"))
        print(inv.total_files)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from pathlib import Path

from app.core.exceptions import ResourceNotFoundException
from app.core.logging import logger
from app.workspace.models import WorkspaceInventory
from app.workspace.scanner import WorkspaceScanner

__all__ = ["InventoryBuilder"]


class InventoryBuilder:
    """
    Builds a :class:`WorkspaceInventory` for a given workspace directory.

    Attributes:
        _scanner: Shared :class:`WorkspaceScanner` instance.
    """

    def __init__(self) -> None:
        """Initialise the builder with its collaborators."""
        self._scanner = WorkspaceScanner()

    def build(self, workspace_id: str, path: Path) -> WorkspaceInventory:
        """
        Scan *path* and return a fully populated :class:`WorkspaceInventory`.

        Args:
            workspace_id: UUID4 string of the workspace being inventoried.
            path:         Absolute :class:`pathlib.Path` to the workspace
                          directory on disk.

        Returns:
            A :class:`~app.workspace.models.WorkspaceInventory` with all
            discovered file records.

        Raises:
            ResourceNotFoundException: If *path* does not point to an
                existing directory.
        """
        if not path.exists() or not path.is_dir():
            logger.warning(
                "InventoryBuilder: workspace '{}' not found at '{}'.",
                workspace_id,
                path,
            )
            raise ResourceNotFoundException(
                resource="workspace",
                identifier=workspace_id,
            )

        logger.info(
            "InventoryBuilder: building inventory for workspace '{}'.",
            workspace_id,
        )

        files = self._scanner.scan(path)

        inventory = WorkspaceInventory(
            workspace_id=workspace_id,
            files=files,
            total_files=len(files),
        )

        logger.info(
            "InventoryBuilder: inventory complete — workspace='{}', files={}.",
            workspace_id,
            inventory.total_files,
        )
        return inventory
