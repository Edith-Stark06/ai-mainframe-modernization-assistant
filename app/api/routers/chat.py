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
from app.api.schemas.chat import (
    ChatErrorCode,
    ChatIndexRequest,
    ChatIndexResponse,
    ChatRequest,
    ChatResponse,
)
from app.rag.orchestration.models import RAGRequest, RAGResult, AICapability
from app.rag.orchestration.service import RAGOrchestrator
from app.api.dependencies.ai import get_ai_orchestrator
from app.api.dependencies.workspace import resolve_workspace_source
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.rag.answer_format import clean_answer
from app.rag.intent import (
    Intent,
    classify_intent,
    conversational_reply,
    retrieval_query,
    wants_broad_context,
)
from app.rag.ingestion import index_program
from app.rag.retrieval.hybrid import HybridRetrievalService
from app.rag.indexing.chroma import ChromaIndex
from app.rag.embeddings.provider import EmbeddingProvider
from app.api.dependencies.rag import get_embedding_provider
from app.core.config import get_settings

router = APIRouter(prefix="/chat", tags=["chat"])

#: How many earlier turns of the conversation are used to understand a follow-up.
_HISTORY_TURNS = 6

#: Chunks retrieved for a question that needs the whole picture ("list the rules",
#: "walk me through an order"): the default few would silently leave parts out.
_BROAD_TOP_K = 16

#: the chat vector index's own fixed identity -- shared by every
#: reader/writer (get_rag_orchestrator's retrieval, index_workspace_file's
#: writes) so they always agree on where chunks live and what dimension
#: they're expected to be.
_CHAT_COLLECTION_NAME = "chat"
_CHAT_INDEX_DIMENSION = 384


def _build_chat_index() -> ChromaIndex:
    settings = get_settings()
    return ChromaIndex(
        persist_directory=str(settings.workspace_dir),
        collection_name=_CHAT_COLLECTION_NAME,
        expected_dimension=_CHAT_INDEX_DIMENSION,
    )


def get_rag_orchestrator(
    ai_orchestrator: AIAnalysisOrchestrator = Depends(get_ai_orchestrator),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> RAGOrchestrator:
    retrieval_service = HybridRetrievalService(embedding_provider, _build_chat_index())
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

    # An invalid request is rejected whatever the message says.
    if request.include_modernization_context and not request.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required when include_modernization_context is true",
        )

    # "hi", "thanks, that works", "bye", "what can you do?" are conversation, not
    # questions about the code: answer them directly. Retrieving and asking the
    # model made it describe the program in reply to "hi".
    intent = classify_intent(request.query)
    if intent is not Intent.QUESTION:
        return ChatResponse(
            query=request.query,
            answer=conversational_reply(intent, request.filename),
            context=[],
            intent=intent.value,
        )

    history = tuple((turn.role, turn.content) for turn in request.history)[
        -_HISTORY_TURNS:
    ]

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
        top_k=(
            max(request.top_k, _BROAD_TOP_K)
            if wants_broad_context(request.query)
            else request.top_k
        ),
        filters=filters,
        ai_capabilities=frozenset(capabilities),
        modernization_context=modernization_data,
        history=history,
        retrieval_query=retrieval_query(request.query, history),
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
            explanation = rag_result.ai_result.explanation
            to_chat = getattr(explanation, "chat_text", None)
            answer = to_chat() if callable(to_chat) else str(explanation)
        elif (
            AICapability.DOCUMENTATION in capabilities
            and rag_result.ai_result.documentation
        ):
            answer = str(rag_result.ai_result.documentation)

    # Number the retrieved chunks 1..N, exactly as the prompt labelled them, so
    # citations read "[2]" and match the Evidence list; tidy the layout.
    refs = {r.chunk_id: n for n, r in enumerate(rag_result.context.results, 1)}
    if answer:
        answer = clean_answer(answer, refs)

    ungrounded = list(rag_result.ungrounded_figures) if answer else []
    if ungrounded:
        answer += (
            "\n\n⚠ Figures not found in the retrieved context (verify before "
            "relying on them): " + ", ".join(ungrounded)
        )

    context = [
        {"id": r.chunk_id, "ref": refs[r.chunk_id], "content": r.content}
        for r in rag_result.context.results
    ]

    return ChatResponse(
        query=request.query,
        answer=answer,
        context=context,
        error=error,
        error_code=error_code,
        modernization_data=modernization_data,
        ungrounded_figures=ungrounded,
    )


@router.post("/index", response_model=ChatIndexResponse)
def index_workspace_file(
    request: ChatIndexRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> ChatIndexResponse:
    """
    Index one workspace file into the chat vector index.

    Before this endpoint, the "chat" ChromaDB collection ``/chat``
    queries was never written to by any real request -- retrieval
    always ran against an empty index regardless of embedding quality.
    This is the missing write side: analyze *filename*, chunk it via
    the existing, fully-tested :class:`~app.knowledge.ingest.KnowledgeIngestor`
    (task #122, previously unwired), embed every chunk with the real
    production :class:`~app.rag.embeddings.provider.EmbeddingProvider`,
    and write them to the same ``ChromaIndex`` ``/chat`` retrieval
    reads from -- so a subsequent chat query about this file can
    actually retrieve real content.

    Args:
        request: Identifies the workspace and file to index.
        workspace_manager: Injected :class:`WorkspaceManager`.
        embedding_provider: Injected, cached production embedding
            provider (see :func:`~app.api.dependencies.rag.get_embedding_provider`).

    Returns:
        How many chunks were indexed, how many
        ``KnowledgeIngestor`` itself rejected (never silently
        dropped), and a per-chunk-type breakdown.

    Note:
        Re-indexing a changed file adds its new chunks (each chunk id
        embeds a content hash, so an edited chunk gets a new id) but
        does not prune the previous version's now-stale chunks from
        the index -- a known, documented limitation of this first
        version, not an oversight.
    """
    source_path = resolve_workspace_source(
        request.workspace_id, request.filename, workspace_manager
    )

    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error(f"Could not read source for indexing {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Could not read source file")

    source_id = source_path.stem.upper()
    identity: dict[str, str | int | float | bool] = {
        "workspace_id": str(request.workspace_id),
        "filename": request.filename,
    }
    try:
        summary = index_program(
            source_id=source_id,
            source_text=source_text,
            source_path=request.filename,
            extra_metadata=identity,
            embedding_provider=embedding_provider,
            index=_build_chat_index(),
            replace_filter=identity,
        )
    except Exception as e:
        logger.error(f"Knowledge ingestion failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Knowledge ingestion failed")

    logger.info(
        "Indexed {} chunk(s) for chat ({} rejected, {} stale replaced) -- "
        "workspace='{}', file='{}'.",
        summary.chunks_indexed,
        summary.chunks_rejected,
        summary.chunks_replaced,
        request.workspace_id,
        request.filename,
    )

    return ChatIndexResponse(
        chunks_indexed=summary.chunks_indexed,
        chunks_rejected=summary.chunks_rejected,
        chunk_types=summary.chunk_types,
        chunks_replaced=summary.chunks_replaced,
    )
