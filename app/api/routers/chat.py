from app.analysis.service import AnalysisService
from app.ingestion.workspace import WorkspaceManager
from app.modernization.flow.generator import generate_flow
from app.modernization.scoring.service import calculate_scores
from app.modernization.recommendations.service import generate_recommendations
from app.api.schemas.modernization import (
    ModernizationPipelineResponse,
    FlowResponse,
    ModernizationScoreResponse,
    RecommendationResponse,
)
from app.core.logging import logger
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from app.api.schemas.chat import ChatRequest, ChatResponse
from app.rag.orchestration.models import RAGRequest, AICapability
from app.rag.orchestration.service import RAGOrchestrator
from app.api.dependencies.ai import get_ai_orchestrator
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.rag.retrieval.service import RetrievalService
from app.rag.indexing.chroma import ChromaIndex
from app.rag.embeddings.provider import DeterministicFakeProvider
from app.core.config import get_settings

router = APIRouter(prefix="/chat", tags=["chat"])


def get_rag_orchestrator(
    ai_orchestrator: AIAnalysisOrchestrator = Depends(get_ai_orchestrator),
) -> RAGOrchestrator:
    # Instantiate retrieval service with mock provider and chroma index
    settings = get_settings()
    index = ChromaIndex(
        persist_directory=str(settings.workspace_dir),
        collection_name="chat",
        expected_dimension=384,
    )
    provider = DeterministicFakeProvider(dimension=384)
    retrieval_service = RetrievalService(provider, index)
    return RAGOrchestrator(
        retrieval_service=retrieval_service, ai_orchestrator=ai_orchestrator
    )




def get_analysis_service() -> AnalysisService:
    return AnalysisService()


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.post("/", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    rag_orchestrator: RAGOrchestrator = Depends(get_rag_orchestrator),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
):
    try:
        capabilities = [AICapability[c] for c in request.ai_capabilities]
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid AI capability requested")

    filters = {"workspace_id": str(request.workspace_id)}
    if request.filename:
        filters["filename"] = request.filename

    rag_request = RAGRequest(
        query=request.query,
        top_k=request.top_k,
        filters=filters,
        ai_capabilities=frozenset(capabilities),
    )

    try:
        rag_result = rag_orchestrator.orchestrate(rag_request)
    except Exception as e:
        logger.error(f"RAG Orchestration failed: {e}")
        # Graceful degradation on complete failure
        return ChatResponse(
            query=request.query,
            answer="",
            context=[],
            error="RAG Orchestration failed due to an internal error.",
        )

    answer = ""
    error = None
    if rag_result.ai_error:
        error = "AI generation failed due to an internal error."
        logger.error(f"AI error: {rag_result.ai_error}")
    elif rag_result.ai_result:
        if (
            AICapability.EXPLANATION in capabilities
            and rag_result.ai_result.explanation
        ):
            answer = str(rag_result.ai_result.explanation)
        elif (
            AICapability.DOCUMENTATION in capabilities
            and rag_result.ai_result.documentation
        ):
            answer = str(rag_result.ai_result.documentation)

    context = [
        {"id": r.chunk_id, "content": r.content} for r in rag_result.context.results
    ]

    modernization_data = None
    if request.include_modernization_context:
        if not request.filename:
            raise HTTPException(status_code=400, detail="Filename is required when include_modernization_context is true")
        try:
            ws = workspace_manager.get(str(request.workspace_id))
            ws_root = Path(ws.path).resolve()
            source_path = (ws_root / request.filename).resolve()
            if source_path.is_relative_to(ws_root) and source_path.exists():
                analysis_result = analysis_service.analyze_file(source_path)
                flow = generate_flow(analysis_result)
                score = calculate_scores(analysis_result, flow)
                recs = generate_recommendations(flow, score)
                mod_resp = ModernizationPipelineResponse(
                    flow=FlowResponse(**flow.to_dict()),
                    score=ModernizationScoreResponse(**score.to_dict()),
                    recommendations=[
                        RecommendationResponse(**r.to_dict()) for r in recs
                    ],
                )
                modernization_data = mod_resp.model_dump()
        except Exception as e:
            logger.error(
                f"Failed to generate modernization context for {request.filename}: {e}"
            )
            # Non-fatal, just omit the data

    return ChatResponse(
        query=request.query,
        answer=answer,
        context=context,
        error=error,
        modernization_data=modernization_data,
    )
