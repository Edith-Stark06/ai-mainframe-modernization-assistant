"""
Phase 8 #122 — provenance-first modernization knowledge ingestion +
retrieval.

    deterministic analysis (Phase 1–5)
        -> KnowledgeIngestor.ingest_program  -> KnowledgeChunk[]  (provenance enforced)
        -> KnowledgeIndex.add                -> embeddings + deterministic store
        -> KnowledgeRetriever.retrieve       -> RetrievedChunk[]  (chunk + provenance + score)

Nothing enters the index or leaves retrieval without a validated
:class:`Provenance`.
"""

from __future__ import annotations

from app.knowledge.chunk import ChunkType, KnowledgeChunk, compute_chunk_id
from app.knowledge.errors import (
    ChunkingError,
    EmbeddingIdentityError,
    KnowledgeError,
    ProvenanceError,
)
from app.knowledge.index import EmbeddingModelId, KnowledgeIndex, RetrievedChunk
from app.knowledge.ingest import IngestionResult, KnowledgeIngestor, merge_results
from app.knowledge.provenance import Provenance, SourceType
from app.knowledge.retrieval import KnowledgeRetriever
from app.knowledge.version import (
    ANALYSIS_CONTRACT_VERSION,
    CHUNKING_VERSION,
    KNOWLEDGE_SCHEMA_VERSION,
)

__all__ = [
    "Provenance",
    "SourceType",
    "KnowledgeChunk",
    "ChunkType",
    "compute_chunk_id",
    "KnowledgeIngestor",
    "IngestionResult",
    "merge_results",
    "EmbeddingModelId",
    "KnowledgeIndex",
    "RetrievedChunk",
    "KnowledgeRetriever",
    "KnowledgeError",
    "ProvenanceError",
    "ChunkingError",
    "EmbeddingIdentityError",
    "KNOWLEDGE_SCHEMA_VERSION",
    "CHUNKING_VERSION",
    "ANALYSIS_CONTRACT_VERSION",
]
