"""
RAG Orchestration Service.

Coordinates RAG requests with RetrievalService and AIAnalysisOrchestrator.
"""

import json
from typing import Any
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.rag.grounding import find_ungrounded_figures
from app.rag.orchestration.models import RAGRequest, RAGResult, RetrievedContext
from app.rag.retrieval.service import RetrievalService
from app.rag.retrieval.models import RetrievalResult


def _labelled(result: RetrievalResult) -> str:
    """A chunk's text preceded by its id, so an answer can cite it."""
    return f"[{result.chunk_id}]\n{result.content}"


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
            # Pass the query as part of the context for the AI.
            ai_context: dict[str, Any] = {"rag_query": request.query}

            # Chunks are labelled with their ids so the answer can cite them.
            # Parser-derived business rules are passed separately: the prompt
            # presents them as authoritative facts that outrank any paraphrase.
            rules = [
                r
                for r in retrieval_results
                if r.metadata.get("chunk_type") == "business_rule"
            ]
            others = [r for r in retrieval_results if r not in rules]
            if others and rules:
                ai_context["business_rules"] = [_labelled(r) for r in rules]
                source = "\n\n".join(_labelled(r) for r in others)
            else:
                source = "\n\n".join(_labelled(r) for r in retrieval_results)

            if request.modernization_context is not None:
                ai_context["modernization_data"] = request.modernization_context

            # Chat is conversational: a small or general model routinely
            # answers "hi" in plain prose rather than the rigid
            # Summary:/Explanation: format. Accept that reply (marked
            # unstructured) rather than failing the whole request.
            ai_result = self.ai_orchestrator.analyze(
                source=source,
                capabilities=set(request.ai_capabilities),
                context=ai_context,
                allow_unstructured=True,
            )

            # Deterministic check that the answer's figures come from the
            # context: an invented threshold is the costly failure here.
            answer_text = "\n".join(
                str(part)
                for part in (ai_result.explanation, ai_result.documentation)
                if part
            )
            grounding_texts = [r.content for r in retrieval_results]
            if request.modernization_context is not None:
                grounding_texts.append(
                    json.dumps(dict(request.modernization_context), default=str)
                )
            ungrounded = find_ungrounded_figures(
                answer_text, grounding_texts, request.query
            )

            return RAGResult(
                request=request,
                context=context,
                ai_result=ai_result,
                ungrounded_figures=tuple(ungrounded),
            )

        except Exception as e:
            # Preserve context but record the AI failure. ai_error_type
            # records the exception's class name (e.g.
            # "LLMProviderUnavailableError") purely for API-layer error
            # classification -- this orchestrator still makes no decision
            # based on it, it only observes and reports.
            return RAGResult(
                request=request,
                context=context,
                ai_error=str(e),
                ai_error_type=type(e).__name__,
            )
