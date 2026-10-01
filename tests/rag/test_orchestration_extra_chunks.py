"""Caller-supplied evidence (extra_chunks) in the RAG orchestrator."""

from __future__ import annotations

from typing import Any

from app.ai.explanation.models import CodeExplanation
from app.ai.orchestration.models import AICapability, AIAnalysisResult
from app.ai.explanation.prompts import build_explanation_prompt
from app.rag.orchestration.models import RAGRequest
from app.rag.orchestration.service import RAGOrchestrator
from app.rag.retrieval.models import RetrievalResult


def _chunk(
    chunk_id: str, content: str, chunk_type: str = "cobol_paragraph"
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="d",
        content=content,
        chunk_index=0,
        metadata={"chunk_type": chunk_type},
        score=0.0,
    )


class _Retrieval:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results

    def search(self, query: str, top_k: int = 5, filter_metadata: Any = None):
        return self.results


class _AI:
    def __init__(self) -> None:
        self.source = ""

    def analyze(self, source, capabilities, context=None, *, allow_unstructured=False):
        self.source = source
        return AIAnalysisResult(
            explanation=CodeExplanation(summary="s", explanation="e"),
            documentation=None,
            context=context or {},
        )


def _run(extra, retrieved, ai=None):
    request = RAGRequest(
        query="did the java compile?",
        ai_capabilities=frozenset([AICapability.EXPLANATION]),
        extra_chunks=tuple(extra),
    )
    return RAGOrchestrator(_Retrieval(retrieved), ai or _AI()).orchestrate(request)  # type: ignore[arg-type]


VALIDATION = _chunk("validation-aaaa1111bbbb2222", "Compilation: PASS", "validation")


def test_supplied_evidence_comes_first_and_is_numbered_first() -> None:
    ai = _AI()
    result = _run([VALIDATION], [_chunk("p1", "MAIN-PARA.")], ai)
    assert [r.chunk_id for r in result.context.results] == [VALIDATION.chunk_id, "p1"]
    assert ai.source.startswith("[1]\nCompilation: PASS")
    assert "[2]\nMAIN-PARA." in ai.source


def test_a_searched_chunk_with_the_same_id_is_not_repeated() -> None:
    result = _run([VALIDATION], [VALIDATION, _chunk("p1", "MAIN-PARA.")])
    assert [r.chunk_id for r in result.context.results] == [VALIDATION.chunk_id, "p1"]


def test_supplied_evidence_alone_is_enough_to_answer() -> None:
    """Retrieval found nothing, but the validation results exist: still answered
    (not reported as 'insufficient context')."""
    result = _run([VALIDATION], [])
    assert result.ai_error is None
    assert result.ai_result is not None


def test_no_supplied_evidence_and_no_search_hits_is_still_insufficient() -> None:
    result = _run([], [])
    assert result.ai_error == "Cannot generate AI response with empty retrieval context"


def test_figures_in_supplied_evidence_count_as_grounded() -> None:
    class Replies(_AI):
        def analyze(
            self, source, capabilities, context=None, *, allow_unstructured=False
        ):
            return AIAnalysisResult(
                explanation=CodeExplanation(
                    summary="All 5 tests passed in 1.3 seconds.", explanation="e"
                ),
                documentation=None,
                context={},
            )

    evidence = _chunk(
        "validation-1", "Tests: PASS - All 5 test(s) passed. took 1.3s", "validation"
    )
    assert _run([evidence], [], Replies()).ungrounded_figures == ()


def test_the_question_prompt_tells_the_model_validation_is_in_scope() -> None:
    prompt = build_explanation_prompt(
        "[1]\nCompilation: PASS", {"rag_query": "did it compile?"}
    )
    assert (
        "converted Java, its compilation, its tests or its validation results" in prompt
    )
    assert "INCONCLUSIVE and NOT_AVAILABLE mean it was not verified" in prompt
    assert "never describe them as passed" in prompt
