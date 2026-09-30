"""
Lexical Ranking (BM25).

Purpose:
    Rank chunks by the exact words they share with a question. Vector search
    captures meaning but can miss a chunk whose decisive token is a literal
    (``50000``, ``HIGH VALUE``, ``WS-TOTAL``); word matching finds those
    reliably. The two are combined in :mod:`app.rag.retrieval.hybrid`.

Responsibilities:
    - :func:`rank_bm25` -- BM25 over a candidate set of chunks, with a bonus
      for exact phrases.

Non-responsibilities:
    - Fetching candidates or fusing rankings (see the hybrid service).

Dependencies:
    - app.rag.retrieval.query, app.rag.retrieval.models

Examples:
    ::

        ranked = rank_bm25("What is the tax rate?", chunks)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from app.rag.retrieval.models import RetrievalResult
from app.rag.retrieval.query import expand_terms, extract_phrases, tokenize

__all__ = ["rank_bm25"]

_K1 = 1.5
_B = 0.75
#: Added once per exact phrase a chunk contains. Large relative to a typical
#: BM25 term score, because a verbatim literal from the question is strong
#: evidence.
_PHRASE_BONUS = 8.0


def rank_bm25(
    query: str, chunks: Sequence[RetrievalResult]
) -> list[tuple[RetrievalResult, float]]:
    """
    Rank *chunks* against *query*, best first.

    Args:
        query: The question (or one part of it).
        chunks: Candidate chunks. Statistics (document frequency, average
            length) are computed over exactly this set.

    Returns:
        ``(chunk, score)`` pairs, score > 0 only, sorted by score descending
        then chunk id (deterministic). Empty when the query has no usable
        terms or nothing matches.
    """
    terms = expand_terms(list(dict.fromkeys(tokenize(query, drop_stopwords=True))))
    phrases = extract_phrases(query)
    if not chunks or not (terms or phrases):
        return []

    docs = [tokenize(c.content) for c in chunks]
    lowered = [c.content.lower() for c in chunks]
    n = len(chunks)
    avg_len = sum(len(d) for d in docs) / n or 1.0
    doc_freq: Counter[str] = Counter()
    for tokens in docs:
        doc_freq.update(set(tokens))

    scored: list[tuple[RetrievalResult, float]] = []
    for chunk, tokens, text in zip(chunks, docs, lowered):
        counts = Counter(tokens)
        length = len(tokens) or 1
        score = 0.0
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            df = doc_freq[term]
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            score += (
                idf * tf * (_K1 + 1.0) / (tf + _K1 * (1.0 - _B + _B * length / avg_len))
            )
        score += _PHRASE_BONUS * sum(1 for p in phrases if p in text)
        if score > 0.0:
            scored.append((chunk, score))

    scored.sort(key=lambda pair: (-pair[1], pair[0].chunk_id))
    return scored
