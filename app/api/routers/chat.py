import uuid
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

def get_rag_orchestrator(ai_orchestrator: AIAnalysisOrchestrator = Depends(get_ai_orchestrator)) -> RAGOrchestrator:
    # Instantiate retrieval service with mock provider and chroma index
    settings = get_settings()
    index = ChromaIndex(persist_directory=str(settings.workspace_dir))
    provider = DeterministicFakeProvider(dimension=384)
    retrieval_service = RetrievalService(embedding_provider=provider, vector_index=index)
    return RAGOrchestrator(retrieval_service=retrieval_service, ai_orchestrator=ai_orchestrator)


@router.post("/", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    rag_orchestrator: RAGOrchestrator = Depends(get_rag_orchestrator)
):
    try:
        capabilities = [AICapability[c] for c in request.ai_capabilities]
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Invalid AI capability: {e}")

    rag_request = RAGRequest(
        query=request.query,
        top_k=request.top_k,
        ai_capabilities=tuple(capabilities)
    )
    
    try:
        rag_result = rag_orchestrator.orchestrate(rag_request)
    except Exception as e:
        # Graceful degradation on complete failure
        return ChatResponse(
            query=request.query,
            answer="",
            context=[],
            error=f"RAG Orchestration failed: {str(e)}"
        )
        
    answer = ""
    error = None
    if rag_result.ai_error:
        error = rag_result.ai_error
    elif rag_result.ai_result:
        if AICapability.EXPLANATION in capabilities and rag_result.ai_result.explanation:
            answer = str(rag_result.ai_result.explanation)
        elif AICapability.DOCUMENTATION in capabilities and rag_result.ai_result.documentation:
            answer = str(rag_result.ai_result.documentation)
            
    context = [{"id": r.id, "content": r.content} for r in rag_result.context.results]
    
    return ChatResponse(
        query=request.query,
        answer=answer,
        context=context,
        error=error
    )
