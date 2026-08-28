"""
RAG Orchestration Service.

Coordinates RAG requests with RetrievalService and AIAnalysisOrchestrator.
"""

from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.rag.orchestration.models import RAGRequest, RAGResult, RetrievedContext
from app.rag.retrieval.service import RetrievalService


class RAGOrchestrator:
    """
    Orchestrator for Retrieval-Augmented Generation workflows.
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        ai_orchestrator: AIAnalysisOrchestrator | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.ai_orchestrator = ai_orchestrator

    def orchestrate(self, request: RAGRequest) -> RAGResult:
        """
        Executes the RAG workflow.

        Args:
            request: The RAGRequest containing query and options.

        Returns:
            RAGResult: The immutable result containing context and AI analysis.
        """
        # 1. Execute Retrieval
        retrieval_results = self.retrieval_service.search(
            query=request.query,
            top_k=request.top_k,
            filter_metadata=request.filters,
        )

        context = RetrievedContext(results=tuple(retrieval_results))

        # 2. Return early if no AI requested
        if not request.ai_capabilities:
            return RAGResult(request=request, context=context)

        # 3. Handle AI unavailable
        if self.ai_orchestrator is None:
            return RAGResult(
                request=request,
                context=context,
                ai_unavailable=True,
                ai_error="AI provider is unavailable",
            )

        # 4. Handle empty retrieval context
        if not retrieval_results:
            return RAGResult(
                request=request,
                context=context,
                ai_error="Cannot generate AI response with empty retrieval context",
            )

        # 5. Execute AI Orchestration
        try:
            # Combine the chunks into a unified source block for the AI.
            source = "\n\n".join(r.content for r in retrieval_results)

            # Pass the query as part of the context for the AI.
            ai_context = {"rag_query": request.query}

            ai_result = self.ai_orchestrator.analyze(
                source=source,
                capabilities=set(request.ai_capabilities),
                context=ai_context,
            )

            return RAGResult(request=request, context=context, ai_result=ai_result)

        except Exception as e:
            # Preserve context but record the AI failure
            return RAGResult(request=request, context=context, ai_error=str(e))
