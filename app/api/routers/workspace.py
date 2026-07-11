"""
Workspace Intelligence API Router.

Purpose:
    Expose the workspace scanning and summary endpoints that allow clients
    to introspect the contents of an uploaded workspace without implementing
    any parser logic.

Responsibilities:
    - Handle ``GET /workspaces/{workspace_id}/inventory`` — scan the workspace
      and return a complete file inventory.
    - Handle ``GET /workspaces/{workspace_id}/summary`` — derive and return
      aggregate project statistics.
    - Delegate all business logic to the service layer.
    - Keep route handlers thin — no business logic here.
    - Log every request at DEBUG level and completion at INFO level.

Dependencies:
    - fastapi                       — :class:`fastapi.APIRouter`,
                                      :func:`fastapi.Path`
    - app.api.schemas.workspace     — response schemas
    - app.core.config               — ``settings.workspace_dir``
    - app.core.exceptions           — :class:`ResourceNotFoundException`
    - app.core.logging              — Loguru logger
    - app.workspace.inventory       — :class:`InventoryBuilder`
    - app.workspace.summary         — :class:`SummaryGenerator`

Examples:
    The router is mounted in ``app.api.router``::

        from app.api.routers.workspace import router as workspace_router
        api_router.include_router(workspace_router)

    Example requests::

        GET /api/v1/workspaces/{workspace_id}/inventory
        GET /api/v1/workspaces/{workspace_id}/summary

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from pathlib import Path

from fastapi import APIRouter

from app.api.schemas.workspace import (
    InventoryResponse,
    ScannedFileSchema,
    SummaryResponse,
    TypeCountSchema,
)
from app.core.config import settings
from app.core.logging import logger
from app.workspace.inventory import InventoryBuilder
from app.workspace.summary import SummaryGenerator

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspace Intelligence"],
)

# ---------------------------------------------------------------------------
# Shared collaborators (instantiated once per module load)
# ---------------------------------------------------------------------------

_inventory_builder = InventoryBuilder()
_summary_generator = SummaryGenerator()

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/inventory",
    response_model=InventoryResponse,
    summary="Get workspace file inventory",
    description=(
        "Recursively scan the workspace directory and return a complete "
        "inventory of all discovered files with their metadata and "
        "classified file types. ZIP archives are transparently expanded."
    ),
)
async def get_inventory(
    workspace_id: str,
) -> InventoryResponse:
    """
    Scan the workspace and return a complete file inventory.

    Args:
        workspace_id: UUID4 string identifying the workspace to scan.

    Returns:
        :class:`~app.api.schemas.workspace.InventoryResponse` with all
        discovered file records.

    Raises:
        ResourceNotFoundException: Propagated from the inventory builder
            when the workspace directory does not exist (→ 404).
    """
    logger.debug("Workspace inventory endpoint: workspace_id='{}'.", workspace_id)

    workspace_path = Path(settings.workspace_dir) / workspace_id
    inventory = _inventory_builder.build(
        workspace_id=workspace_id,
        path=workspace_path,
    )

    file_schemas = [ScannedFileSchema(**f.model_dump()) for f in inventory.files]

    response = InventoryResponse(
        workspace_id=inventory.workspace_id,
        files=file_schemas,
        total_files=inventory.total_files,
        scanned_at=inventory.scanned_at,
    )

    logger.info(
        "Workspace inventory endpoint: completed — workspace='{}', files={}.",
        workspace_id,
        inventory.total_files,
    )
    return response


@router.get(
    "/{workspace_id}/summary",
    response_model=SummaryResponse,
    summary="Get workspace project summary",
    description=(
        "Scan the workspace directory, classify all discovered files, and "
        "return aggregate project statistics: file counts by type and "
        "total cumulative size."
    ),
)
async def get_summary(
    workspace_id: str,
) -> SummaryResponse:
    """
    Scan the workspace and return aggregate project statistics.

    Args:
        workspace_id: UUID4 string identifying the workspace to summarise.

    Returns:
        :class:`~app.api.schemas.workspace.SummaryResponse` with per-type
        file counts and cumulative byte size.

    Raises:
        ResourceNotFoundException: Propagated when the workspace directory
            does not exist (→ 404).
    """
    logger.debug("Workspace summary endpoint: workspace_id='{}'.", workspace_id)

    workspace_path = Path(settings.workspace_dir) / workspace_id
    inventory = _inventory_builder.build(
        workspace_id=workspace_id,
        path=workspace_path,
    )
    summary = _summary_generator.generate(inventory)

    type_schemas = [
        TypeCountSchema(file_type=tc.file_type, count=tc.count)
        for tc in summary.by_type
    ]

    response = SummaryResponse(
        workspace_id=summary.workspace_id,
        total_files=summary.total_files,
        by_type=type_schemas,
        total_size_bytes=summary.total_size_bytes,
        scanned_at=summary.scanned_at,
    )

    logger.info(
        "Workspace summary endpoint: completed — workspace='{}', "
        "files={}, types={}.",
        workspace_id,
        summary.total_files,
        len(type_schemas),
    )
    return response
