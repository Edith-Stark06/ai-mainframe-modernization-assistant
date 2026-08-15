"""
Analysis API Router.

Purpose:
    Expose the ``POST /api/v1/workspaces/{workspace_id}/analyze`` endpoint
    that triggers COBOL source analysis through the production
    :class:`~app.analysis.service.AnalysisService`.

Responsibilities:
    - Resolve the requested source file within an existing workspace.
    - Validate the source file extension against allowed analysis types.
    - Delegate analysis to :class:`~app.analysis.service.AnalysisService`.
    - Serialize the :class:`~app.analysis.models.AnalysisResult` using
      TASK-043 serializers.
    - Return a typed :class:`~app.api.schemas.analysis.AnalysisResponse`.
    - Keep route handlers thin — no business logic here.
    - Log every request at DEBUG level and completion at INFO level.

Non-responsibilities:
    - Compiler pipeline implementation.
    - AST / IR / diagnostic serialization logic.
    - Workspace creation or file ingestion.

Dependencies:
    - fastapi                       — :class:`fastapi.APIRouter`
    - app.api.schemas.analysis      — :class:`AnalysisRequest`,
                                      :class:`AnalysisResponse`
    - app.core.config               — ``settings.workspace_dir``
    - app.core.exceptions           — :class:`ResourceNotFoundException`,
                                      :class:`ValidationException`
    - app.core.logging              — Loguru logger
    - app.analysis.service          — :class:`AnalysisService`
    - app.analysis.serializers.ast  — :func:`serialize_ast`
    - app.analysis.serializers.ir   — :func:`serialize_ir`
    - app.analysis.serializers.diagnostics — :func:`serialize_diagnostics`

Examples:
    The router is mounted in ``app.api.router``::

        from app.api.routers.analysis import router as analysis_router
        api_router.include_router(analysis_router)

    Example request::

        POST /api/v1/workspaces/ws-uuid/analyze
        Content-Type: application/json

        { "filename": "payroll.cbl" }

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter

from app.analysis.serializers.ast import serialize_ast
from app.analysis.serializers.diagnostics import serialize_diagnostics
from app.analysis.serializers.ir import serialize_ir
from app.analysis.service import AnalysisService
from app.api.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisSourceMetadata,
)
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.logging import logger
from app.ingestion.workspace import WorkspaceManager
from app.workspace.inventory import InventoryBuilder

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/workspaces",
    tags=["Analysis"],
)

# ---------------------------------------------------------------------------
# Supported analysis extensions
# ---------------------------------------------------------------------------

_ALLOWED_ANALYSIS_EXTENSIONS: frozenset[str] = frozenset({".cbl", ".cob"})

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/analyze",
    response_model=AnalysisResponse,
    summary="Analyze a COBOL source file",
    description=(
        "Resolve a COBOL source file within the specified workspace, "
        "run the full analysis pipeline through AnalysisService, and "
        "return the generated Java source, serialized AST, serialized IR, "
        "and any collected diagnostics."
    ),
)
async def analyze_source(
    workspace_id: str,
    request: AnalysisRequest,
) -> AnalysisResponse:
    """
    Analyze a COBOL source file within an existing workspace.

    Args:
        workspace_id: UUID4 string identifying the workspace.
        request:      :class:`AnalysisRequest` containing the source filename.

    Returns:
        :class:`~app.api.schemas.analysis.AnalysisResponse` with the
        serialized analysis result.

    Raises:
        ResourceNotFoundException: If the workspace or source file does not
            exist (→ 404).
        ValidationException: If the requested file has an unsupported
            extension (→ 422).
    """
    logger.debug(
        "Analysis endpoint: workspace_id='{}', filename='{}'.",
        workspace_id,
        request.filename,
    )

    # ------------------------------------------------------------------
    # Resolve workspace through WorkspaceManager
    # ------------------------------------------------------------------
    workspace_manager = WorkspaceManager()
    try:
        workspace_record = workspace_manager.get(workspace_id)
    except ResourceNotFoundException:
        logger.warning("Analysis endpoint: workspace '{}' not found.", workspace_id)
        raise
    workspace_root = Path(workspace_record.path)

    # ------------------------------------------------------------------
    # Resolve and validate source file
    # ------------------------------------------------------------------
    source_path = (workspace_root / request.filename).resolve()

    # Path traversal prevention: ensure the resolved path is within the workspace.
    try:
        source_path.relative_to(workspace_root)
    except ValueError:
        logger.warning(
            "Analysis endpoint: path traversal attempt '{}' in workspace '{}'.",
            request.filename,
            workspace_id,
        )
        raise ValidationException(
            message="Invalid filename: path traversal is not allowed.",
            details={"filename": request.filename},
        )

    if not source_path.is_file():
        logger.warning(
            "Analysis endpoint: source file '{}' not found in workspace '{}'.",
            request.filename,
            workspace_id,
        )
        raise ResourceNotFoundException(
            resource="source",
            identifier=request.filename,
        )

    if source_path.suffix.lower() not in _ALLOWED_ANALYSIS_EXTENSIONS:
        logger.warning(
            "Analysis endpoint: unsupported extension '{}' for file '{}'.",
            source_path.suffix,
            request.filename,
        )
        raise ValidationException(
            message=(
                f"Unsupported file extension '{source_path.suffix}'. "
                f"Allowed extensions: {', '.join(sorted(_ALLOWED_ANALYSIS_EXTENSIONS))}."
            ),
            details={"filename": request.filename, "extension": source_path.suffix},
        )

    # ------------------------------------------------------------------
    # Generate correlation ID
    # ------------------------------------------------------------------
    analysis_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Compute source metadata
    # ------------------------------------------------------------------
    inventory_builder = InventoryBuilder()
    inventory = inventory_builder.build(workspace_id, workspace_root)

    target_path = str(source_path)
    scanned_file = next((f for f in inventory.files if f.path == target_path), None)

    if not scanned_file:
        logger.warning(
            "Analysis endpoint: source file '{}' not found in workspace inventory '{}'.",
            request.filename,
            workspace_id,
        )
        raise ResourceNotFoundException(
            resource="source",
            identifier=request.filename,
        )

    source_metadata = AnalysisSourceMetadata(
        extension=scanned_file.extension,
        size_bytes=scanned_file.size_bytes,
        sha256=scanned_file.sha256,
    )

    # ------------------------------------------------------------------
    # Run analysis
    # ------------------------------------------------------------------
    service = AnalysisService()
    result = service.analyze_file(source_path)

    # ------------------------------------------------------------------
    # Serialize result
    # ------------------------------------------------------------------
    serialized_ast = serialize_ast(result.ast) if result.ast is not None else None
    serialized_ir = serialize_ir(result.ir) if result.ir is not None else None
    serialized_diagnostics = serialize_diagnostics(
        result.semantic_diagnostics + result.backend_diagnostics
    )

    response = AnalysisResponse(
        success=result.success,
        analysis_id=analysis_id,
        workspace_id=workspace_id,
        filename=request.filename,
        source_metadata=source_metadata,
        java_source=result.java_source,
        ast=serialized_ast,
        ir=serialized_ir,
        diagnostics=serialized_diagnostics,
        error=str(result.error) if result.error is not None else None,
    )

    logger.info(
        "Analysis endpoint: completed — workspace='{}', file='{}', success={}.",
        workspace_id,
        request.filename,
        result.success,
    )
    return response
