"""
Java Generation ("COBOL <-> Java") API Router.

Purpose:
    Expose the existing #126 Java code generation
    (``app.java_modernization.generation.generate_project``) and #127
    compilation (``app.java_modernization.compilation.JavaCompiler``)
    over HTTP. No Java is generated or compiled here -- this router only
    resolves the request, runs the existing pipeline, and shapes the
    result into :class:`JavaGenerationResponse`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.schemas.java_generation import JavaGenerationResponse
from app.api.schemas.modernization import ModernizationRequest
from app.api.services.pipeline import run_pipeline_for_source
from app.ingestion.workspace import WorkspaceManager

router = APIRouter(
    prefix="/workspaces/{workspace_id}/modernization", tags=["modernization"]
)


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.post("/java", response_model=JavaGenerationResponse)
def get_java_generation(
    workspace_id: uuid.UUID,
    request: ModernizationRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> JavaGenerationResponse:
    """
    Return the real #126 generated Java project (with its COBOL source
    mappings) and the real #127 compilation result, or an explicit
    ``available=False`` + reason if generation could not run.
    """
    bundle, mb = run_pipeline_for_source(
        workspace_id, request.filename, workspace_manager
    )

    reason = mb.architecture_error or mb.generation_error
    return JavaGenerationResponse(
        workspace_id=str(workspace_id),
        filename=request.filename,
        available=mb.project is not None,
        reason=reason,
        project=mb.project,
        compilation=mb.compilation,
    )
