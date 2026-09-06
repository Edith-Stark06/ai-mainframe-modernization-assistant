import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from app.api.schemas.modernization import (
    ModernizationRequest,
    ModernizationPipelineResponse,
    ModernizationIntelligenceResponse,
    FlowResponse,
    ModernizationScoreResponse,
    RecommendationResponse,
)
from app.analysis.service import AnalysisService
from app.modernization.flow.generator import generate_flow
from app.modernization.intelligence import analyze_modernization_intelligence
from app.modernization.scoring.service import calculate_scores
from app.modernization.recommendations.service import generate_recommendations
from app.ingestion.workspace import WorkspaceManager
from app.core.exceptions import ResourceNotFoundException

router = APIRouter(
    prefix="/workspaces/{workspace_id}/modernization", tags=["modernization"]
)


def get_analysis_service() -> AnalysisService:
    return AnalysisService()


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.post("/pipeline", response_model=ModernizationPipelineResponse)
def execute_modernization_pipeline(
    workspace_id: uuid.UUID,
    request: ModernizationRequest,
    analysis_service: AnalysisService = Depends(get_analysis_service),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    """
    Executes the full modernization pipeline (Flow -> Scoring -> Recommendations).
    """
    try:
        ws = workspace_manager.get(str(workspace_id))
    except ResourceNotFoundException:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from pathlib import Path

    try:
        ws_root = Path(ws.path).resolve()
        source_path = (ws_root / request.filename).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid filename format")

    if not source_path.is_relative_to(ws_root):
        raise HTTPException(status_code=403, detail="Forbidden path traversal detected")

    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source file not found")

    from app.core.logging import logger

    # Generate AnalysisResult
    try:
        analysis_result = analysis_service.analyze_file(source_path)
    except Exception as e:
        logger.error(f"Analysis failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed")

    # Generate Flow
    try:
        flow = generate_flow(analysis_result)
    except Exception as e:
        logger.error(f"Flow generation failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Flow generation failed")

    # Calculate Scores
    try:
        score = calculate_scores(analysis_result, flow)
    except Exception as e:
        logger.error(f"Scoring failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Scoring failed")

    # Generate Recommendations
    try:
        recs = generate_recommendations(flow, score)
    except Exception as e:
        logger.error(f"Recommendation generation failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Recommendation generation failed")

    return ModernizationPipelineResponse(
        flow=FlowResponse(**flow.to_dict()),
        score=ModernizationScoreResponse(**score.to_dict()),
        recommendations=[RecommendationResponse(**r.to_dict()) for r in recs],
    )


def _resolve_workspace_source(
    workspace_id: uuid.UUID,
    filename: str,
    workspace_manager: WorkspaceManager,
) -> Path:
    """Shared workspace lookup + path-traversal guard for modernization routes."""
    try:
        ws = workspace_manager.get(str(workspace_id))
    except ResourceNotFoundException:
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        ws_root = Path(ws.path).resolve()
        source_path = (ws_root / filename).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid filename format")

    if not source_path.is_relative_to(ws_root):
        raise HTTPException(status_code=403, detail="Forbidden path traversal detected")
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source file not found")
    return source_path


@router.post("/intelligence", response_model=ModernizationIntelligenceResponse)
def execute_modernization_intelligence(
    workspace_id: uuid.UUID,
    request: ModernizationRequest,
    analysis_service: AnalysisService = Depends(get_analysis_service),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    """
    Phase 4 Modernization Intelligence: deterministic business rules (#112),
    modernization risks (#113), and strategy recommendations (#114).

    Reuses the same Phase 1-3 analysis and CFG as ``/pipeline``; it does
    not run any LLM. Output ordering and identifiers are stable for a
    given source.
    """
    from app.core.logging import logger

    source_path = _resolve_workspace_source(
        workspace_id, request.filename, workspace_manager
    )

    try:
        analysis_result = analysis_service.analyze_file(source_path)
    except Exception as e:
        logger.error(f"Analysis failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed")

    try:
        result = analyze_modernization_intelligence(analysis_result)
    except Exception as e:
        logger.error(f"Modernization intelligence failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Modernization intelligence failed")

    payload = result.to_dict()
    return ModernizationIntelligenceResponse(**payload)
