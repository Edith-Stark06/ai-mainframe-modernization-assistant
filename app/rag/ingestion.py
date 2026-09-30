"""
Program Indexing Pipeline.

Purpose:
    The single place that turns one COBOL program into indexed, retrievable
    chunks: deterministic ingestion (:class:`~app.knowledge.ingest.KnowledgeIngestor`),
    the knowledge-to-RAG bridge, embedding, and the vector index. The chat
    endpoint and the retrieval evaluation both call it, so what is measured is
    exactly what is served.

Responsibilities:
    - :func:`index_program` -- ingest, embed and add one program's chunks,
      first removing the chunks a previous indexing of the *same file* left
      behind, so re-indexing an edited file never leaves stale chunks that
      compete with the current ones for retrieval slots.

Non-responsibilities:
    - Reading the source file or resolving workspace paths (the caller does).
    - Retrieval and answering.

Dependencies:
    - app.knowledge.ingest, app.rag.knowledge_bridge, app.rag.embeddings.service,
      app.rag.indexing.base

Examples:
    ::

        summary = index_program(
            source_id="PAYROLL",
            source_text=text,
            source_path="payroll.cbl",
            extra_metadata={"workspace_id": ws, "filename": "payroll.cbl"},
            embedding_provider=provider,
            index=index,
            replace_filter={"workspace_id": ws, "filename": "payroll.cbl"},
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.knowledge.ingest import KnowledgeIngestor
from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.embeddings.service import EmbeddingService
from app.rag.indexing.base import VectorIndex
from app.rag.knowledge_bridge import to_rag_chunks

__all__ = ["IndexingSummary", "index_program"]


@dataclass(frozen=True)
class IndexingSummary:
    """
    What one :func:`index_program` call did.

    Attributes:
        chunks_indexed: Chunks embedded and added.
        chunks_rejected: Chunks the ingestor itself refused (never dropped
            silently).
        chunk_types: ``{chunk type: count}`` of the indexed chunks.
        chunks_replaced: Stale chunks from an earlier indexing of the same
            file that were removed first.
    """

    chunks_indexed: int
    chunks_rejected: int
    chunk_types: dict[str, int] = field(default_factory=dict)
    chunks_replaced: int = 0


def index_program(
    *,
    source_id: str,
    source_text: str,
    source_path: str,
    extra_metadata: dict[str, Any],
    embedding_provider: EmbeddingProvider,
    index: VectorIndex,
    replace_filter: dict[str, str | int | float | bool] | None = None,
) -> IndexingSummary:
    """
    Ingest one program and add its chunks to *index*.

    Args:
        source_id: Identifier used for the program's provenance.
        source_text: The COBOL source.
        source_path: Path recorded in each chunk's provenance.
        extra_metadata: Flat metadata merged into every chunk (for example
            ``workspace_id`` / ``filename``, the filters chat retrieval uses).
        embedding_provider: Embeds the chunk text.
        index: Where the chunks go.
        replace_filter: Metadata identifying *this file's* earlier chunks
            (typically ``workspace_id`` + ``filename``). When given, and the
            new ingestion produced chunks, those earlier chunks are deleted
            before adding. Nothing is deleted if ingestion produced no chunks,
            so a bad edit cannot wipe a good index.

    Returns:
        An :class:`IndexingSummary`.

    Raises:
        Exception: Whatever ingestion or embedding raises; the index is
            untouched in that case (deletion happens only after both succeed).
    """
    ingestion_result = KnowledgeIngestor().ingest_program(
        source_id, source_text, source_path=source_path
    )
    rag_chunks = to_rag_chunks(ingestion_result, extra_metadata=extra_metadata)

    replaced = 0
    if rag_chunks:
        embeddings = EmbeddingService(embedding_provider).embed_chunks(rag_chunks)
        if replace_filter:
            try:
                replaced = index.delete(replace_filter)
            except NotImplementedError:
                logger.debug("Index cannot delete; stale chunks (if any) are kept.")
        index.add(embeddings, rag_chunks)

    return IndexingSummary(
        chunks_indexed=len(rag_chunks),
        chunks_rejected=len(ingestion_result.rejected),
        chunk_types=dict(ingestion_result.by_type()),
        chunks_replaced=replaced,
    )
