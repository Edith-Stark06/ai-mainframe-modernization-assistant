"""
Modernization Report API Router.

Purpose:
    Aggregate the existing Phase 1-11 artifacts (already exposed
    individually by the analysis/intelligence/architecture/java/
    validation routes) into one modernization-dossier response. Nothing
    is recomputed independently -- this router runs the same
    ``run_pipeline_for_source`` + ``compute_validation_stages`` calls
    the other new routes use and only assembles their results.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.schemas.modernization import ModernizationRequest
from app.api.schemas.report import ModernizationReportResponse
from app.api.schemas.validation import StageStatus
from app.api.services.pipeline import run_pipeline_for_source
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


@router.post("/report", response_model=ModernizationReportResponse)
def get_modernization_report(
    workspace_id: uuid.UUID,
    request: ModernizationRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> ModernizationReportResponse:
    """Aggregate real backend results into one modernization dossier.
    Every unavailable stage remains explicitly unavailable/inconclusive
    -- see ``unresolved_issues`` for the consolidated list."""
    bundle, mb = run_pipeline_for_source(
        workspace_id, request.filename, workspace_manager
    )
    stages = compute_validation_stages(bundle, mb)
    overall = compute_overall_status(stages)

    return ModernizationReportResponse(
        workspace_id=str(workspace_id),
        filename=request.filename,
        source_id=bundle.source_id,
        analysis_success=bundle.success,
        paragraphs=list(bundle.paragraphs),
        business_rules=bundle.business_rules,
        risks=bundle.risks,
        strategy=bundle.strategy,
        dependencies=bundle.dependencies,
        coverage=bundle.coverage,
        confidence=bundle.confidence,
        architecture=mb.architecture,
        architecture_reason=mb.architecture_error,
        project=mb.project,
        generation_reason=mb.generation_error,
        compilation=mb.compilation,
        validation_stages=stages,
        overall_status=overall,
        unsupported_syntax=(bundle.coverage or {}).get("unsupported_syntax"),
        unresolved_issues=[
            f"{s.stage}: {s.summary}"
            for s in stages
            if s.status is not StageStatus.PASS
        ],
    )
