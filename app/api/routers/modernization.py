import uuid
from fastapi import APIRouter, Depends, HTTPException
from app.api.schemas.modernization import (
    ModernizationRequest,
    ModernizationPipelineResponse,
    FlowResponse,
    ModernizationScoreResponse,
    RecommendationResponse,
)
from app.analysis.service import AnalysisService
from app.modernization.flow.generator import generate_flow
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
    except ResourceNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))

    from pathlib import Path

    source_path = Path(ws.path) / request.filename
    if not source_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Source file not found: {request.filename}"
        )

    # Generate AnalysisResult
    try:
        analysis_result = analysis_service.analyze_file(source_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    # Generate Flow
    try:
        flow = generate_flow(analysis_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Flow generation failed: {str(e)}")

    # Calculate Scores
    try:
        score = calculate_scores(analysis_result, flow)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {str(e)}")

    # Generate Recommendations
    try:
        recs = generate_recommendations(flow, score)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Recommendation generation failed: {str(e)}"
        )

    return ModernizationPipelineResponse(
        flow=FlowResponse(**flow.to_dict()),
        score=ModernizationScoreResponse(**score.to_dict()),
        recommendations=[RecommendationResponse(**r.to_dict()) for r in recs],
    )
