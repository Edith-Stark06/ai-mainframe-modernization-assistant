"""
Architecture API Router.

Purpose:
    Expose the existing, deterministic #125 Java-architecture-generation
    capability (``app.java_modernization.architecture.build_architecture``)
    over HTTP so the Phase 12 frontend can render real architecture data
    instead of an honest "not available" stub.

Non-responsibilities:
    Architecture derivation logic itself -- entirely owned by #125.
    This router only resolves the request, runs the existing pipeline,
    and shapes the result into :class:`ArchitectureResponse`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.schemas.architecture import ArchitectureResponse
from app.api.schemas.modernization import ModernizationRequest
from app.api.services.pipeline import run_pipeline_for_source
from app.ingestion.workspace import WorkspaceManager

router = APIRouter(
    prefix="/workspaces/{workspace_id}/modernization", tags=["modernization"]
)


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.post("/architecture", response_model=ArchitectureResponse)
def get_architecture(
    workspace_id: uuid.UUID,
    request: ModernizationRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> ArchitectureResponse:
    """
    Return the real #125 evidence-based Java architecture for a source
    file, or an explicit ``available=False`` + reason if it could not be
    derived (e.g. the source has no usable AST). Never a fabricated
    architecture.
    """
    bundle, mb = run_pipeline_for_source(
        workspace_id, request.filename, workspace_manager
    )

    return ArchitectureResponse(
        workspace_id=str(workspace_id),
        filename=request.filename,
        available=mb.architecture is not None,
        reason=mb.architecture_error,
        architecture=mb.architecture,
    )
