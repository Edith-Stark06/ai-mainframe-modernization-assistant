"""
RAG API Dependencies.

Purpose:
    Provide the production embedding provider as an overridable FastAPI
    dependency, mirroring ``app.api.dependencies.ai``'s
    ``get_llm_provider`` seam. Before this module,
    ``app.api.routers.chat``'s ``get_rag_orchestrator`` constructed a
    :class:`~app.rag.embeddings.provider.DeterministicFakeProvider`
    inline with no override point -- every real request embedded chat
    queries with a hash-based fake with no semantic meaning at all,
    since nothing indexed real content either (see
    :func:`get_embedding_provider`'s own note on why a real provider
    alone does not fix retrieval quality).

Responsibilities:
    - :func:`get_embedding_provider` -- the production
      :class:`~app.rag.embeddings.provider.EmbeddingProvider`, cached
      as a process-wide singleton (model loading takes real time; this
      must not happen per-request).

Non-responsibilities:
    - Populating the vector index with real workspace content -- see
      ``app.knowledge.ingest.KnowledgeIngestor`` (task #122), which
      exists and is fully tested but, like this provider before now,
      has no API wiring calling it. Wiring ingestion into a real
      endpoint is a separate, larger piece of work than swapping the
      embedding provider alone.

Dependencies:
    - app.rag.embeddings.provider -- EmbeddingProvider, SentenceTransformerProvider

Examples:
    Overriding in a test::

        from app.api.dependencies.rag import get_embedding_provider
        from app.rag.embeddings.provider import DeterministicFakeProvider

        app.dependency_overrides[get_embedding_provider] = (
            lambda: DeterministicFakeProvider(dimension=384)
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import threading
from functools import lru_cache

from app.rag.embeddings.provider import EmbeddingProvider, SentenceTransformerProvider

__all__ = ["get_embedding_provider"]

# functools.lru_cache keeps its cache consistent across threads but does
# NOT stop two threads that both miss from each computing the value. With
# the startup warm-up (app.main) running in a background thread, a
# request arriving mid-warm-up would otherwise start a second, parallel
# multi-second model load (double the memory, slower for both). The lock
# makes concurrent callers wait for the one in-flight load instead.
_load_lock = threading.Lock()


@lru_cache
def _load_embedding_provider() -> EmbeddingProvider:
    return SentenceTransformerProvider()


def get_embedding_provider() -> EmbeddingProvider:
    """
    Return the production embedding provider, loaded once per process.

    Returns:
        A :class:`~app.rag.embeddings.provider.SentenceTransformerProvider`
        (384-dimensional, matching every ``ChromaIndex`` this codebase
        constructs). Cached since loading the model is expensive and the
        provider is stateless/thread-safe to reuse across requests -- the
        same process-wide-singleton idea
        :func:`app.core.config.get_settings` uses. Safe to call from
        several threads at once: exactly one performs the load and the
        rest wait for its result.
    """
    with _load_lock:
        return _load_embedding_provider()
