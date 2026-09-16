"""
Validation Center API Router.

Purpose:
    Expose an explicit, honest PASS / FAIL / INCONCLUSIVE / NOT_AVAILABLE
    status for every stage of the deterministic pipeline (parser,
    analysis, coverage, confidence, Java generation, compilation, Java
    tests, COBOL tests, behavioral equivalence, risks, unsupported
    syntax, self-repair). Classification logic lives in
    ``app.api.services.validation_stages`` and is reused unchanged by
    the Report endpoint.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.schemas.modernization import ModernizationRequest
from app.api.schemas.validation import ValidationResponse
from app.api.services.pipeline import run_pipeline_for_source
from app.api.services.pipeline_cache import PipelineCache, get_pipeline_cache
from app.api.services.validation_stages import (
    compute_overall_status,
    compute_validation_stages,
)
from app.ingestion.workspace import WorkspaceManager

router = APIRouter(
    prefix="/workspaces/{workspace_id}/modernization", tags=["modernization"]
)


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.post("/validation", response_model=ValidationResponse)
def get_validation(
    workspace_id: uuid.UUID,
    request: ModernizationRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    cache: PipelineCache = Depends(get_pipeline_cache),
) -> ValidationResponse:
    """
    Return the real per-stage validation status. A stage the pipeline
    could not run reports NOT_AVAILABLE, never PASS -- in particular,
    Behavioral Equivalence is INCONCLUSIVE (not PASS) whenever COBOL
    execution is unavailable, and Compilation is NOT_AVAILABLE (not
    PASS) whenever it did not run.
    """
    bundle, mb = run_pipeline_for_source(
        workspace_id, request.filename, workspace_manager, cache
    )
    stages = compute_validation_stages(bundle, mb)

    return ValidationResponse(
        workspace_id=str(workspace_id),
        filename=request.filename,
        stages=stages,
        overall_status=compute_overall_status(stages),
    )
