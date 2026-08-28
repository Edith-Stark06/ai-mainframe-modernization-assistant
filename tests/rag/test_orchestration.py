import pytest
from typing import Any

from app.rag.orchestration.models import RAGRequest, RAGResult, RetrievedContext
from app.rag.orchestration.service import RAGOrchestrator
from app.ai.orchestration.models import AICapability, AIAnalysisResult
from app.rag.retrieval.models import RetrievalResult
from app.ai.explanation.models import CodeExplanation
from app.ai.documentation.models import Documentation, DocumentationSection


class DummyRetrievalService:
    def __init__(self, results: list[RetrievalResult], should_fail: bool = False):
        self._results = results
        self.should_fail = should_fail
        self.last_query = ""

    def search(
        self, query: str, top_k: int = 5, filter_metadata: Any = None
    ) -> list[RetrievalResult]:
        if self.should_fail:
            raise ValueError("Retrieval failed")
        self.last_query = query
        return self._results


class DummyAIOrchestrator:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.last_source = ""

    def analyze(
        self,
        source: str,
        capabilities: set[AICapability],
        context: dict[str, Any] | None = None,
    ) -> AIAnalysisResult:
        if self.should_fail:
            raise RuntimeError("AI failed")
        self.last_source = source
        return AIAnalysisResult(
            explanation=(
                CodeExplanation(summary="sum", explanation="det")
                if AICapability.EXPLANATION in capabilities
                else None
            ),
            documentation=(
                Documentation(
                    title="title",
                    overview="overview",
                    sections=(DocumentationSection("h", "c"),),
                )
                if AICapability.DOCUMENTATION in capabilities
                else None
            ),
            context=context or {},
        )


def _make_retrieval_result(chunk_id: str, content: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="doc1",
        content=content,
        chunk_index=0,
        metadata={},
        score=0.5,
    )


def test_rag_request_validation() -> None:
    with pytest.raises(ValueError, match="Query cannot be empty"):
        RAGRequest(query="   ")

    with pytest.raises(ValueError, match="top_k must be a positive integer"):
        RAGRequest(query="test", top_k=0)


def test_rag_request_immutability() -> None:
    req = RAGRequest(
        query="test",
        filters={"type": "code"},
        ai_capabilities=frozenset([AICapability.EXPLANATION]),
    )
    # Underlying types should be frozen mapping and frozenset
    with pytest.raises(TypeError):
        req.filters["type"] = "doc"  # type: ignore


def test_orchestration_retrieval_only() -> None:
    results = [_make_retrieval_result("c1", "content 1")]
    retrieval = DummyRetrievalService(results)
    orchestrator = RAGOrchestrator(retrieval_service=retrieval)

    req = RAGRequest(query="test query")
    res = orchestrator.orchestrate(req)

    assert not res.ai_unavailable
    assert res.ai_error is None
    assert res.ai_result is None
    assert len(res.context.results) == 1
    assert res.context.results[0].chunk_id == "c1"


def test_orchestration_ai_success() -> None:
    results = [
        _make_retrieval_result("c1", "content 1"),
        _make_retrieval_result("c2", "content 2"),
    ]
    retrieval = DummyRetrievalService(results)
    ai_orch = DummyAIOrchestrator()
    orchestrator = RAGOrchestrator(retrieval, ai_orch)

    req = RAGRequest(
        query="test query", ai_capabilities=frozenset([AICapability.EXPLANATION])
    )
    res = orchestrator.orchestrate(req)

    assert res.ai_error is None
    assert not res.ai_unavailable
    assert res.ai_result is not None
    assert res.ai_result.explanation is not None
    assert ai_orch.last_source == "content 1\n\ncontent 2"
    assert len(res.context.results) == 2


def test_orchestration_ai_unavailable() -> None:
    results = [_make_retrieval_result("c1", "content 1")]
    retrieval = DummyRetrievalService(results)
    # No AI orchestrator provided
    orchestrator = RAGOrchestrator(retrieval_service=retrieval)

    req = RAGRequest(
        query="test query", ai_capabilities=frozenset([AICapability.EXPLANATION])
    )
    res = orchestrator.orchestrate(req)

    assert res.ai_unavailable is True
    assert res.ai_error == "AI provider is unavailable"
    assert res.ai_result is None
    # Context must be preserved
    assert len(res.context.results) == 1


def test_orchestration_ai_failure_preserves_context() -> None:
    results = [_make_retrieval_result("c1", "content 1")]
    retrieval = DummyRetrievalService(results)
    ai_orch = DummyAIOrchestrator(should_fail=True)
    orchestrator = RAGOrchestrator(retrieval, ai_orch)

    req = RAGRequest(
        query="test query", ai_capabilities=frozenset([AICapability.EXPLANATION])
    )
    res = orchestrator.orchestrate(req)

    assert res.ai_error == "AI failed"
    assert res.ai_result is None
    # Context must be preserved
    assert len(res.context.results) == 1


def test_orchestration_empty_retrieval_preserves_context() -> None:
    retrieval = DummyRetrievalService([])
    ai_orch = DummyAIOrchestrator()
    orchestrator = RAGOrchestrator(retrieval, ai_orch)

    req = RAGRequest(
        query="test query", ai_capabilities=frozenset([AICapability.EXPLANATION])
    )
    res = orchestrator.orchestrate(req)

    assert "empty retrieval context" in str(res.ai_error)
    assert res.ai_result is None
    # Context is safely empty
    assert len(res.context.results) == 0


def test_orchestrator_retrieval_failure_propagates() -> None:
    retrieval = DummyRetrievalService([], should_fail=True)
    orchestrator = RAGOrchestrator(retrieval)

    req = RAGRequest(query="test query")
    with pytest.raises(ValueError, match="Retrieval failed"):
        orchestrator.orchestrate(req)


def test_rag_result_serialization() -> None:
    req = RAGRequest(
        query="test query",
        filters={"k": "v"},
        ai_capabilities=frozenset([AICapability.EXPLANATION]),
    )
    ctx = RetrievedContext(results=(_make_retrieval_result("c1", "content"),))
    ai_res = AIAnalysisResult(
        explanation=CodeExplanation(summary="s", explanation="d"),
        documentation=None,
        context={"rag_query": "test query"},
    )
    res = RAGResult(request=req, context=ctx, ai_result=ai_res)

    d = res.to_dict()
    assert d["request"]["query"] == "test query"
    assert d["request"]["filters"] == {"k": "v"}
    assert d["request"]["ai_capabilities"] == ["EXPLANATION"]
    assert len(d["context"]["results"]) == 1
    assert d["context"]["results"][0]["chunk_id"] == "c1"
    assert not d["ai_unavailable"]
    assert d["ai_error"] is None
    assert d["ai_result"]["explanation"]["summary"] == "s"
    assert d["ai_result"]["documentation"] is None
    assert d["ai_result"]["context"]["rag_query"] == "test query"
