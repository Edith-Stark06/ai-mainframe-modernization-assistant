"""HybridRetrievalService: multi-part questions, exact text, dedupe, fallback."""

from __future__ import annotations

import pytest

from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.embeddings.service import EmbeddingService
from app.rag.indexing.memory import InMemoryIndex
from app.rag.models import KnowledgeChunk
from app.rag.retrieval.hybrid import HybridRetrievalService
from app.rag.retrieval.models import RetrievalResult
from app.rag.retrieval.service import RetrievalService

DIM = 64
PROVIDER = DeterministicFakeProvider(dimension=DIM)

THRESHOLD = (
    "Business rule BR-007: When WS-TOTAL >= 50000, set WS-STATUS to 'HIGH VALUE'."
)
DISCOUNT = (
    "Business rule BR-003: When WS-CUSTOMER-TYPE = 'R', set WS-DISCOUNT-RATE to 0.10."
)


def _chunk(cid: str, text: str, index: int, **meta) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=cid, document_id="doc", content=text, chunk_index=index, metadata=meta
    )


def _build(chunks: list[KnowledgeChunk], index_cls=InMemoryIndex) -> InMemoryIndex:
    index = index_cls(expected_dimension=DIM)
    index.add(EmbeddingService(PROVIDER).embed_chunks(chunks), chunks)
    return index


def _corpus(extra_meta: dict | None = None) -> list[KnowledgeChunk]:
    meta = extra_meta or {}
    chunks = [
        _chunk("threshold", THRESHOLD, 0, **meta),
        _chunk("discount", DISCOUNT, 1, **meta),
    ]
    # Unrelated filler so a fact cannot be found by luck.
    for i in range(30):
        chunks.append(
            _chunk(
                f"filler{i}",
                f"MOVE {i} TO WS-COUNTER-{i}. DISPLAY 'STEP {i}'.",
                2 + i,
                **meta,
            )
        )
    return chunks


def _ids(results: list[RetrievalResult]) -> list[str]:
    return [r.chunk_id for r in results]


def test_two_part_question_retrieves_a_fact_for_each_part() -> None:
    service = HybridRetrievalService(PROVIDER, _build(_corpus()))
    got = _ids(
        service.search(
            "At what order total does the status become HIGH VALUE, and what "
            "happens to the customer's discount rate for type R?",
            top_k=4,
        )
    )
    assert "threshold" in got
    assert "discount" in got


def test_exact_literal_is_found_even_when_vectors_do_not_help() -> None:
    service = HybridRetrievalService(PROVIDER, _build(_corpus()))
    assert _ids(service.search("What happens at 50000?", top_k=3))[0] == "threshold"


def test_chunks_with_identical_text_are_returned_once() -> None:
    chunks = _corpus()
    chunks.append(_chunk("threshold-old", THRESHOLD, 99))  # a stale copy
    service = HybridRetrievalService(PROVIDER, _build(chunks))
    got = _ids(service.search("When is the status HIGH VALUE?", top_k=5))
    assert sum(1 for cid in got if cid in ("threshold", "threshold-old")) == 1


def test_results_are_limited_to_top_k_and_ordered_best_first() -> None:
    service = HybridRetrievalService(PROVIDER, _build(_corpus()))
    results = service.search("HIGH VALUE 50000", top_k=3)
    assert len(results) == 3
    scores = [r.score for r in results]
    assert scores == sorted(scores)  # lower (more negative) is better


def test_metadata_filter_restricts_lexical_and_vector_candidates() -> None:
    chunks = _corpus({"filename": "a.cbl"}) + [
        _chunk(
            "other-file", THRESHOLD + " (copy in another file)", 200, filename="b.cbl"
        )
    ]
    service = HybridRetrievalService(PROVIDER, _build(chunks))
    got = _ids(
        service.search(
            "HIGH VALUE 50000", top_k=5, filter_metadata={"filename": "a.cbl"}
        )
    )
    assert "other-file" not in got
    assert "threshold" in got


def test_index_that_cannot_list_chunks_falls_back_to_vector_search() -> None:
    class NoListing(InMemoryIndex):
        def list_chunks(self, filter_metadata=None):  # type: ignore[override]
            raise NotImplementedError

    index = _build(_corpus(), NoListing)
    results = HybridRetrievalService(PROVIDER, index).search("HIGH VALUE", top_k=3)
    assert len(results) == 3  # still answers from vectors


def test_is_deterministic() -> None:
    service = HybridRetrievalService(PROVIDER, _build(_corpus()))
    q = "What is the discount for type R, and when is an order HIGH VALUE?"
    assert _ids(service.search(q, top_k=5)) == _ids(service.search(q, top_k=5))


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_query_is_rejected(query: str) -> None:
    with pytest.raises(ValueError, match="empty"):
        HybridRetrievalService(PROVIDER, _build(_corpus())).search(query)


@pytest.mark.parametrize("top_k", [0, -1])
def test_non_positive_top_k_is_rejected(top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k"):
        HybridRetrievalService(PROVIDER, _build(_corpus())).search("x y z", top_k=top_k)


def test_is_a_drop_in_replacement_for_the_vector_service() -> None:
    assert issubclass(HybridRetrievalService, RetrievalService)


def test_each_part_of_a_multi_part_question_is_searched_on_its_own() -> None:
    """The vector half must see each part separately: one vector for a
    two-topic question is a blur of both, which is how a fact got dropped."""

    class Recording(DeterministicFakeProvider):
        def __init__(self) -> None:
            super().__init__(dimension=DIM)
            self.embedded: list[str] = []

        def embed(self, text: str):
            self.embedded.append(text)
            return super().embed(text)

    provider = Recording()
    index = _build(_corpus())
    question = (
        "At what order total does the status become HIGH VALUE, and what "
        "happens to the customer's discount rate for type R?"
    )
    HybridRetrievalService(provider, index).search(question, top_k=3)
    assert provider.embedded == [
        question,
        "At what order total does the status become HIGH VALUE",
        "what happens to the customer's discount rate for type R?",
    ]


def test_a_single_part_question_is_embedded_once() -> None:
    class Recording(DeterministicFakeProvider):
        def __init__(self) -> None:
            super().__init__(dimension=DIM)
            self.embedded: list[str] = []

        def embed(self, text: str):
            self.embedded.append(text)
            return super().embed(text)

    provider = Recording()
    HybridRetrievalService(provider, _build(_corpus())).search(
        "When is the status HIGH VALUE?", top_k=3
    )
    assert provider.embedded == ["When is the status HIGH VALUE?"]
