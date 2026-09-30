"""RAGOrchestrator: labelled chunks, pinned parser rules, figure check."""

from __future__ import annotations

from typing import Any

from app.ai.explanation.models import CodeExplanation
from app.ai.orchestration.models import AICapability, AIAnalysisResult
from app.rag.orchestration.models import RAGRequest
from app.rag.orchestration.service import RAGOrchestrator
from app.rag.retrieval.models import RetrievalResult


class _Retrieval:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self._results = results

    def search(self, query: str, top_k: int = 5, filter_metadata: Any = None):
        return self._results


class _AI:
    """Records what it was given; answers with a fixed explanation."""

    def __init__(self, summary: str = "s", explanation: str = "e") -> None:
        self.summary, self.explanation = summary, explanation
        self.source = ""
        self.context: dict[str, Any] = {}

    def analyze(self, source, capabilities, context=None, *, allow_unstructured=False):
        self.source = source
        self.context = dict(context or {})
        return AIAnalysisResult(
            explanation=CodeExplanation(
                summary=self.summary, explanation=self.explanation
            ),
            documentation=None,
            context=context or {},
        )


def _result(chunk_id: str, content: str, chunk_type: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="doc1",
        content=content,
        chunk_index=0,
        metadata={"chunk_type": chunk_type},
        score=0.5,
    )


def _request() -> RAGRequest:
    return RAGRequest(
        query="When is an order HIGH VALUE?",
        ai_capabilities=frozenset([AICapability.EXPLANATION]),
    )


def _run(results: list[RetrievalResult], ai: _AI):
    return RAGOrchestrator(_Retrieval(results), ai).orchestrate(_request())  # type: ignore[arg-type]


def test_business_rules_are_passed_separately_from_other_chunks() -> None:
    ai = _AI()
    _run(
        [
            _result("p1", "IF WS-TOTAL >= 50000 ...", "cobol_paragraph"),
            _result("br1", "Business rule BR-007: WS-TOTAL >= 50000", "business_rule"),
        ],
        ai,
    )
    assert ai.context["business_rules"] == [
        "[br1]\nBusiness rule BR-007: WS-TOTAL >= 50000"
    ]
    assert ai.source == "[p1]\nIF WS-TOTAL >= 50000 ..."


def test_only_business_rules_still_give_the_model_a_source() -> None:
    ai = _AI()
    _run([_result("br1", "Business rule BR-007", "business_rule")], ai)
    assert ai.source == "[br1]\nBusiness rule BR-007"
    assert "business_rules" not in ai.context


def test_figure_not_in_context_is_reported() -> None:
    ai = _AI(summary="The limit is 7,500.", explanation="Above 7,500 it flags.")
    res = _run([_result("p1", "IF WS-TOTAL >= 50000", "cobol_paragraph")], ai)
    assert res.ungrounded_figures == ("7,500",)
    assert res.to_dict()["ungrounded_figures"] == ["7,500"]


def test_grounded_answer_reports_nothing() -> None:
    ai = _AI(summary="At 50,000 or more.", explanation="WS-TOTAL >= 50000.")
    res = _run([_result("p1", "IF WS-TOTAL >= 50000", "cobol_paragraph")], ai)
    assert res.ungrounded_figures == ()
