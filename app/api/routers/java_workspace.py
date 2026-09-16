"""
Java Workspace API Router.

Purpose:
    Expose real generated Java (#126), compilation (#127), and
    behavioral validation (#131) status together with the real,
    deterministic Phase 11 candidate identity -- replacing the honest
    "not available" stub the Phase 12 frontend previously showed for
    this screen.

Non-responsibilities:
    Running the Phase 11 quality/self-repair loop. That requires a
    configured ``LLMProvider`` (a required parameter of
    ``run_quality_loop()``), and no provider is configured in this
    environment (``app.api.dependencies.ai.get_llm_provider()`` returns
    ``None``, a pre-existing, repo-wide fact). This router NEVER calls
    ``run_quality_loop()`` with no provider, and never infers or
    fabricates repair history, iterations, or an audit trail that never
    happened -- those fields are reported as empty / NOT_AVAILABLE with
    an explicit reason instead.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.schemas.java_workspace import JavaWorkspaceResponse
from app.api.schemas.modernization import ModernizationRequest
from app.api.services.pipeline import run_pipeline_for_source
from app.api.services.pipeline_cache import PipelineCache, get_pipeline_cache
from app.api.services.validation_stages import compute_validation_stages
from app.behavioral.extraction.extractor import extract_behavioral_tests
from app.ingestion.workspace import WorkspaceManager
from app.quality_loop.candidate import first_candidate

router = APIRouter(
    prefix="/workspaces/{workspace_id}/modernization", tags=["modernization"]
)

QUALITY_LOOP_UNAVAILABLE_REASON = (
    "AI provider not configured -- app.api.dependencies.ai.get_llm_provider() "
    "returns None in this environment, so the Phase 11 quality/self-repair "
    "loop has never been run for this analysis. No iterations, repair "
    "history, human-review checkpoints, or audit trail exist yet."
)


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.post("/java-workspace", response_model=JavaWorkspaceResponse)
def get_java_workspace(
    workspace_id: uuid.UUID,
    request: ModernizationRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    cache: PipelineCache = Depends(get_pipeline_cache),
) -> JavaWorkspaceResponse:
    """
    Return the real generated Java/compilation/behavioral status for a
    source file, plus its real deterministic candidate identity. Quality
    -loop execution fields (iterations, repair history, human review,
    audit trail) are honestly empty -- see ``quality_loop_reason``.
    """
    bundle, mb = run_pipeline_for_source(
        workspace_id, request.filename, workspace_manager, cache
    )

    # Reuse the SAME stage classification /validation already computes --
    # never a second, independent PASS/FAIL/INCONCLUSIVE/NOT_AVAILABLE
    # judgment for the same underlying facts.
    stages = {s.stage: s for s in compute_validation_stages(bundle, mb)}
    compilation_status = stages["Compilation"].status
    behavioral_status = stages["Behavioral Equivalence"].status

    current_candidate = None
    if mb.architecture is not None and mb.project is not None:
        suite = extract_behavioral_tests(bundle)
        current_candidate = first_candidate(
            bundle=bundle,
            architecture=mb.architecture,
            project=mb.project,
            test_suite=suite,
        )

    return JavaWorkspaceResponse(
        workspace_id=str(workspace_id),
        filename=request.filename,
        generation_available=mb.project is not None,
        generation_reason=mb.architecture_error or mb.generation_error,
        project=mb.project,
        compilation=mb.compilation,
        compilation_status=compilation_status,
        behavioral_status=behavioral_status,
        behavioral=mb.behavioral,
        current_candidate=current_candidate,
        candidate_lineage=[current_candidate] if current_candidate is not None else [],
        quality_loop_available=False,
        quality_loop_reason=QUALITY_LOOP_UNAVAILABLE_REASON,
        loop_state=None,
        final_status=None,
        stop_reason=None,
        iteration_count=0,
        repair_count=0,
        iterations=[],
        human_review_required=False,
        human_review_checkpoints=[],
        audit_trail=[],
    )
