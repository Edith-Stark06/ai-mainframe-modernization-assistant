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
from app.api.schemas.chat import ChatErrorCode, ChatRequest, ChatResponse
from app.rag.orchestration.models import RAGRequest, RAGResult, AICapability
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


#: exact, stable string RAGOrchestrator.orchestrate() uses for its one
#: "empty retrieval context" case (app/rag/orchestration/service.py) --
#: matched verbatim, never modified, since RAG semantics are frozen.
_EMPTY_CONTEXT_MESSAGE = "Cannot generate AI response with empty retrieval context"

_SAFE_MESSAGES: dict[ChatErrorCode, str] = {
    ChatErrorCode.LLM_PROVIDER_NOT_CONFIGURED: (
        "AI provider is not configured in this environment."
    ),
    ChatErrorCode.LLM_PROVIDER_UNAVAILABLE: (
        "The configured AI provider is temporarily unavailable."
    ),
    ChatErrorCode.LLM_GENERATION_FAILED: (
        "The configured provider failed to generate a response."
    ),
    ChatErrorCode.INSUFFICIENT_CONTEXT: (
        "There is not enough verified evidence to answer this question."
    ),
}


def _classify_ai_error(rag_result: RAGResult) -> tuple[ChatErrorCode, str]:
    """
    Map a RAGResult carrying ai_error into exactly one ChatErrorCode +
    safe message. Distinguishes "no provider configured" from "empty
    retrieval context" from "the provider itself is down" from "some
    other generation failure" -- never a single generic string for all
    four, per the review's explicit error-contract requirement.
    """
    if rag_result.ai_unavailable:
        code = ChatErrorCode.LLM_PROVIDER_NOT_CONFIGURED
    elif rag_result.ai_error == _EMPTY_CONTEXT_MESSAGE:
        code = ChatErrorCode.INSUFFICIENT_CONTEXT
    elif rag_result.ai_error_type == "LLMProviderUnavailableError":
        code = ChatErrorCode.LLM_PROVIDER_UNAVAILABLE
    else:
        code = ChatErrorCode.LLM_GENERATION_FAILED
    return code, _SAFE_MESSAGES[code]


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

    modernization_data = None
    if request.include_modernization_context:
        if not request.filename:
            raise HTTPException(
                status_code=400,
                detail="Filename is required when include_modernization_context is true",
            )
        try:
            ws = workspace_manager.get(str(request.workspace_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="Workspace not found")

        ws_root = Path(ws.path).resolve()
        source_path = (ws_root / request.filename).resolve()

        if not source_path.is_relative_to(ws_root):
            raise HTTPException(status_code=403, detail="Path traversal not allowed")

        if not source_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        try:
            analysis_result = analysis_service.analyze_file(source_path)
            flow = generate_flow(analysis_result)
            score = calculate_scores(analysis_result, flow)
            recs = generate_recommendations(flow, score)
            mod_resp = ModernizationPipelineResponse(
                flow=FlowResponse(**flow.to_dict()),
                score=ModernizationScoreResponse(**score.to_dict()),
                recommendations=[RecommendationResponse(**r.to_dict()) for r in recs],
            )
            modernization_data = mod_resp.model_dump()
        except Exception as e:
            logger.error(
                f"Failed to generate modernization context for {request.filename}: {e}"
            )
            # Raise generic 500 error to avoid exposing internal details
            raise HTTPException(
                status_code=500, detail="Internal server error during analysis"
            )

    rag_request = RAGRequest(
        query=request.query,
        top_k=request.top_k,
        filters=filters,
        ai_capabilities=frozenset(capabilities),
        modernization_context=modernization_data,
    )

    try:
        rag_result = rag_orchestrator.orchestrate(rag_request)
    except Exception as e:
        logger.error(f"RAG Orchestration failed: {e}")
        # Graceful degradation on complete failure. This is a genuinely
        # unclassified failure -- see ChatErrorCode.GROUNDED_CONTEXT_UNAVAILABLE's
        # docstring for why it cannot be distinguished from any other
        # orchestration-level exception without modifying RAG semantics.
        return ChatResponse(
            query=request.query,
            answer="",
            context=[],
            error="RAG Orchestration failed due to an internal error.",
            error_code=ChatErrorCode.INTERNAL_ERROR,
            modernization_data=modernization_data,
        )

    answer = ""
    error = None
    error_code = None
    if rag_result.ai_error:
        error_code, error = _classify_ai_error(rag_result)
        logger.error(f"AI error [{error_code.value}]: {rag_result.ai_error}")
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

    return ChatResponse(
        query=request.query,
        answer=answer,
        context=context,
        error=error,
        error_code=error_code,
        modernization_data=modernization_data,
    )
