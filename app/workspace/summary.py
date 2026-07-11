"""
Workspace Summary Generator.

Purpose:
    Derive aggregate project statistics from a
    :class:`~app.workspace.models.WorkspaceInventory` and produce a
    :class:`~app.workspace.models.WorkspaceSummary`.

Responsibilities:
    - Count discovered files per :class:`~app.workspace.models.FileType`.
    - Compute the total cumulative size of all files in bytes.
    - Sort the per-type counts in descending order by count.
    - Return a :class:`WorkspaceSummary` that bundles all statistics.
    - Never perform I/O — operates purely on in-memory model objects.

Dependencies:
    - collections — :class:`collections.Counter` for aggregation
    - app.workspace.models — :class:`WorkspaceInventory`,
                             :class:`WorkspaceSummary`,
                             :class:`TypeCount`,
                             :class:`FileType`
    - app.core.logging     — Loguru logger

Examples:
    Generating a summary from an inventory::

        from app.workspace.summary import SummaryGenerator

        gen = SummaryGenerator()
        summary = gen.generate(inventory)
        for tc in summary.by_type:
            print(tc.file_type, tc.count)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from collections import Counter

from app.core.logging import logger
from app.workspace.models import (
    FileType,
    TypeCount,
    WorkspaceInventory,
    WorkspaceSummary,
)

__all__ = ["SummaryGenerator"]


class SummaryGenerator:
    """
    Derives :class:`WorkspaceSummary` statistics from a :class:`WorkspaceInventory`.

    The generator is stateless and may be called multiple times with
    different inventories.
    """

    def generate(self, inventory: WorkspaceInventory) -> WorkspaceSummary:
        """
        Compute summary statistics for *inventory*.

        Args:
            inventory: A populated :class:`~app.workspace.models.WorkspaceInventory`
                       produced by :class:`~app.workspace.inventory.InventoryBuilder`.

        Returns:
            A :class:`~app.workspace.models.WorkspaceSummary` containing
            per-type counts (sorted descending) and total byte size.

        Examples:
            >>> gen = SummaryGenerator()
            >>> summary = gen.generate(inventory)
            >>> summary.total_files
            3
        """
        logger.info(
            "SummaryGenerator: computing summary for workspace '{}'.",
            inventory.workspace_id,
        )

        type_counter: Counter[str] = Counter()
        total_bytes = 0

        for scanned_file in inventory.files:
            # ``use_enum_values=True`` on ScannedFile means file_type is stored
            # as the string value — cast back to enum for consistent lookup.
            ft_value = scanned_file.file_type
            type_counter[str(ft_value)] += 1
            total_bytes += scanned_file.size_bytes

        # Build TypeCount list sorted by count descending
        by_type: list[TypeCount] = []
        for ft in FileType:
            count = type_counter.get(ft.value, 0)
            if count > 0:
                by_type.append(TypeCount(file_type=ft, count=count))

        by_type.sort(key=lambda tc: tc.count, reverse=True)

        summary = WorkspaceSummary(
            workspace_id=inventory.workspace_id,
            total_files=inventory.total_files,
            by_type=by_type,
            total_size_bytes=total_bytes,
        )

        logger.info(
            "SummaryGenerator: summary complete — workspace='{}', "
            "files={}, size={} bytes, types={}.",
            inventory.workspace_id,
            summary.total_files,
            summary.total_size_bytes,
            len(by_type),
        )
        return summary
