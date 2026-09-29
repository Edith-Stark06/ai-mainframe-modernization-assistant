"""
Knowledge -> RAG Chunk Bridge.

Purpose:
    Adapt :class:`app.knowledge.chunk.KnowledgeChunk` (task #122's
    richer, provenance-enforcing chunk model, produced by
    :class:`~app.knowledge.ingest.KnowledgeIngestor`) into
    :class:`app.rag.models.KnowledgeChunk` (the plain shape
    :class:`~app.rag.embeddings.service.EmbeddingService` and
    :class:`~app.rag.indexing.chroma.ChromaIndex` actually consume).
    These are two distinct classes that happen to share a name in
    different modules, with incompatible fields (``chunk_id`` vs
    ``id``, no ``document_id``/``chunk_index`` on the knowledge side at
    all) -- this mismatch is exactly the missing link that left
    ``KnowledgeIngestor`` fully built and tested (task #122) but never
    wired into the real vector index the ``/chat`` endpoint queries.

Responsibilities:
    - :func:`to_rag_chunks` -- convert every chunk in an
      :class:`~app.knowledge.ingest.IngestionResult`, merging in any
      caller-supplied *extra_metadata* (e.g. ``workspace_id``,
      ``filename``) so the result is filterable the same way
      ``/chat`` already filters retrieval.

Non-responsibilities:
    - Ingestion itself (:mod:`app.knowledge.ingest`).
    - Embedding or indexing (:mod:`app.rag.embeddings.service`,
      :mod:`app.rag.indexing.chroma`).

Dependencies:
    - app.knowledge.ingest -- IngestionResult
    - app.rag.models -- KnowledgeChunk

Examples:
    Converting an ingestion result for indexing::

        from app.knowledge.ingest import KnowledgeIngestor
        from app.rag.knowledge_bridge import to_rag_chunks

        result = KnowledgeIngestor().ingest_program("PAYROLL", source)
        chunks = to_rag_chunks(
            result, extra_metadata={"workspace_id": ws_id, "filename": "payroll.cbl"}
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.knowledge.ingest import IngestionResult
from app.rag.models import KnowledgeChunk as RagKnowledgeChunk

__all__ = ["to_rag_chunks"]


def to_rag_chunks(
    result: IngestionResult, *, extra_metadata: dict[str, Any] | None = None
) -> list[RagKnowledgeChunk]:
    """
    Convert *result*'s chunks into the RAG layer's own chunk shape.

    Args:
        result: An :class:`~app.knowledge.ingest.IngestionResult`
            (already deterministically ordered by
            ``KnowledgeIngestor.ingest_bundle``).
        extra_metadata: Additional flat, JSON-safe metadata merged into
            every converted chunk (e.g. ``workspace_id``, ``filename``,
            for the exact retrieval filters ``/chat`` already applies).
            Overrides any same-named key the source chunk already
            carries.

    Returns:
        One :class:`~app.rag.models.KnowledgeChunk` per input chunk, in
        the same order -- ``chunk_index`` is that position, since the
        knowledge-layer chunk has no index of its own. Empty if
        *result* has no chunks.
    """
    extra = extra_metadata or {}
    converted: list[RagKnowledgeChunk] = []
    for index, chunk in enumerate(result.chunks):
        metadata = dict(chunk.index_metadata())
        metadata.update(extra)
        converted.append(
            RagKnowledgeChunk(
                id=chunk.chunk_id,
                document_id=chunk.provenance.source_id,
                content=chunk.content,
                chunk_index=index,
                metadata=metadata,
            )
        )
    return converted
