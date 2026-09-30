"""
Hybrid Retrieval.

Purpose:
    Retrieval that does not lose a fact because of how the question is phrased.
    Measured on this project's sample program, vector-only search returned all
    the needed evidence for only 64% of questions; it dropped half of a
    two-part question and could not find a decisive literal. This service adds
    what was missing and keeps the same interface as
    :class:`~app.rag.retrieval.service.RetrievalService`.

Responsibilities:
    - :class:`HybridRetrievalService` -- for each part of the question, run a
      vector search *and* an exact-word (BM25) search over the same filtered
      chunks, fuse every ranking with reciprocal-rank fusion, remove chunks
      with identical text, and return the top ``top_k``.

Non-responsibilities:
    - Embedding (the provider does it) and answer generation.

Dependencies:
    - app.rag.retrieval.service, .query, .lexical

Examples:
    ::

        service = HybridRetrievalService(embedding_provider, index)
        results = service.search("When is an order HIGH VALUE?", top_k=5)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from loguru import logger

from app.rag.retrieval.lexical import rank_bm25
from app.rag.retrieval.models import RetrievalResult
from app.rag.retrieval.query import split_question
from app.rag.retrieval.service import RetrievalService

__all__ = ["HybridRetrievalService"]

#: Reciprocal-rank-fusion constant (the standard value): damps the advantage
#: of a first-place rank so several mid-ranked votes can outweigh one.
_RRF_K = 60

#: Each ranking contributes at least this many candidates, regardless of
#: ``top_k``, so a fact ranked just outside the final cut can still be voted in.
_MIN_CANDIDATES = 20


def _text_key(result: RetrievalResult) -> str:
    """Whitespace/case-insensitive identity of a chunk's text."""
    return " ".join(result.content.lower().split())


class HybridRetrievalService(RetrievalService):
    """
    Vector + exact-word retrieval over each part of the question.

    Same constructor and ``search`` signature as :class:`RetrievalService`.
    If the index cannot list its chunks (``NotImplementedError``), the exact-
    word half is skipped and the vector half still runs per part.
    """

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Mapping[str, str | int | float | bool] | None = None,
    ) -> list[RetrievalResult]:
        """
        Search for chunks relevant to *query*.

        Args:
            query: The question.
            top_k: Maximum chunks to return.
            filter_metadata: Restrict to chunks with this metadata.

        Returns:
            Up to *top_k* chunks, best first, with unique text. ``score`` is
            the negated fusion score (lower is better, matching the distance
            convention of the vector index).

        Raises:
            ValueError: *query* is blank or *top_k* is not positive.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or whitespace-only")
        if top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        flt = dict(filter_metadata) if filter_metadata is not None else None
        n_candidates = max(top_k * 3, _MIN_CANDIDATES)
        parts = split_question(query)

        candidates: list[RetrievalResult] | None
        try:
            candidates = self.index.list_chunks(flt)
        except NotImplementedError:
            candidates = None
            logger.debug("Index cannot list chunks; using vector search only.")

        fused: dict[str, float] = {}
        by_id: dict[str, RetrievalResult] = {}

        def vote(ranking: list[RetrievalResult]) -> None:
            for rank, result in enumerate(ranking, 1):
                fused[result.chunk_id] = fused.get(result.chunk_id, 0.0) + 1.0 / (
                    _RRF_K + rank
                )
                by_id.setdefault(result.chunk_id, result)

        for part in parts:
            vector = self.index.search(
                query_vector=self.provider.embed(part),
                top_k=n_candidates,
                filter_metadata=flt,
            )
            vote(list(vector))
            if candidates:
                vote([c for c, _ in rank_bm25(part, candidates)][:n_candidates])

        ordered = sorted(fused, key=lambda cid: (-fused[cid], cid))
        results: list[RetrievalResult] = []
        seen_text: set[str] = set()
        for chunk_id in ordered:
            result = by_id[chunk_id]
            key = _text_key(result)
            if key in seen_text:
                continue
            seen_text.add(key)
            results.append(replace(result, score=-fused[chunk_id]))
            if len(results) == top_k:
                break
        return results
