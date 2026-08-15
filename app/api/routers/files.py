"""
Workspace File Source Context API Router.

Purpose:
    Expose the ``GET /api/v1/workspaces/{workspace_id}/files/{filename}``
    endpoint that returns the source content and metadata of a file
    already present inside a workspace.

Responsibilities:
    - Resolve the requested workspace through :class:`~app.ingestion.workspace.WorkspaceManager`.
    - Resolve the requested filename relative to the resolved workspace root.
    - Prevent path traversal and absolute path attacks.
    - Verify the file exists before reading.
    - Read the file using the repository's existing UTF-8 convention.
    - Return source content together with readily available metadata.
    - Keep route handlers thin — no business logic here.
    - Log every request at DEBUG level and completion at INFO level.

Non-responsibilities:
    - Compiler pipeline implementation.
    - File ingestion or validation.
    - Workspace creation or deletion.
    - Analysis orchestration.

Dependencies:
    - fastapi                       — :class:`fastapi.APIRouter`
    - app.api.schemas.files          — :class:`FileResponse`
    - app.core.exceptions           — :class:`ResourceNotFoundException`,
                                      :class:`ValidationException`
    - app.core.logging              — Loguru logger
    - app.ingestion.workspace       — :class:`WorkspaceManager`

Examples:
    The router is mounted in ``app.api.router``::

        from app.api.routers.files import router as files_router
        api_router.include_router(files_router)

    Example request::

        GET /api/v1/workspaces/ws-uuid/files/payroll.cbl

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter

from app.api.schemas.files import FileResponse
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.logging import logger
from app.ingestion.workspace import WorkspaceManager

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspace Files"],
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/files/{filename:path}",
    response_model=FileResponse,
    summary="Get workspace source file content",
    description=(
        "Resolve a source file within the specified workspace, read its "
        "UTF-8 content, and return the content together with basic file "
        "metadata. The endpoint is read-only and does not trigger analysis."
    ),
)
async def get_source_file(
    workspace_id: str,
    filename: str,
) -> FileResponse:
    """
    Return the source content and metadata of a file within a workspace.

    Args:
        workspace_id: UUID4 string identifying the workspace.
        filename:     Basename of the file to retrieve.

    Returns:
        :class:`~app.api.schemas.files.FileResponse` with the file content
        and metadata.

    Raises:
        ResourceNotFoundException: If the workspace or source file does not
            exist (→ 404).
        ValidationException: If the requested filename performs path
            traversal or is an absolute path (→ 422).
    """
    logger.debug(
        "File source endpoint: workspace_id='{}', filename='{}'.",
        workspace_id,
        filename,
    )

    # ------------------------------------------------------------------
    # Resolve workspace through WorkspaceManager
    # ------------------------------------------------------------------
    workspace_manager = WorkspaceManager()
    try:
        workspace_record = workspace_manager.get(workspace_id)
    except ResourceNotFoundException:
        logger.warning("File source endpoint: workspace '{}' not found.", workspace_id)
        raise
    workspace_root = Path(workspace_record.path)

    # ------------------------------------------------------------------
    # Resolve and validate source file
    # ------------------------------------------------------------------
    source_path = (workspace_root / filename).resolve()

    # Path traversal prevention: ensure the resolved path is within the workspace.
    try:
        source_path.relative_to(workspace_root)
    except ValueError:
        logger.warning(
            "File source endpoint: path traversal attempt '{}' in workspace '{}'.",
            filename,
            workspace_id,
        )
        raise ValidationException(
            message="Invalid filename: path traversal is not allowed.",
            details={"filename": filename},
        )

    if not source_path.is_file():
        logger.warning(
            "File source endpoint: source file '{}' not found in workspace '{}'.",
            filename,
            workspace_id,
        )
        raise ResourceNotFoundException(
            resource="source",
            identifier=filename,
        )

    # ------------------------------------------------------------------
    # Read content and compute metadata
    # ------------------------------------------------------------------
    content = source_path.read_text(encoding="utf-8")
    size_bytes = source_path.stat().st_size
    sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    extension = source_path.suffix.lower()

    response = FileResponse(
        success=True,
        workspace_id=workspace_id,
        filename=filename,
        content=content,
        extension=extension,
        size_bytes=size_bytes,
        sha256=sha256,
    )

    logger.info(
        "File source endpoint: completed — workspace='{}', file='{}', size={}.",
        workspace_id,
        filename,
        size_bytes,
    )
    return response
