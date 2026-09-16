"""
Embedding + index abstraction for Phase 8 knowledge (#122 Steps 4-6).

* :class:`EmbeddingModelId` — the identity of the embedding model
  (provider / model / version / dimension). Its ``identity`` hash is part
  of the index identity, so vectors from two different models can never
  be silently mixed.
* :class:`KnowledgeIndex` — binds one :class:`~app.rag.embeddings.provider.EmbeddingProvider`
  to one deterministic vector store. ``add`` refuses any chunk without
  valid provenance; ``search`` returns :class:`RetrievedChunk` objects
  that keep the whole chunk + provenance + score (never bare text).

The default store is in-memory and deterministic — no production vector
DB. A :class:`~app.rag.indexing.base.VectorIndex` can be plugged in later
without touching callers.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable

from app.knowledge.chunk import KnowledgeChunk
from app.knowledge.errors import EmbeddingIdentityError, IndexError_, ProvenanceError
from app.knowledge.provenance import Provenance
from app.rag.embeddings.provider import EmbeddingProvider

__all__ = [
    "EmbeddingModelId",
    "RetrievedChunk",
    "KnowledgeIndex",
]


@dataclass(frozen=True)
class EmbeddingModelId:
    provider: str
    model: str
    version: str
    dimension: int

    def __post_init__(self) -> None:
        if self.dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        for f in (self.provider, self.model, self.version):
            if not f:
                raise ValueError("embedding identity fields must be non-empty")

    @property
    def identity(self) -> str:
        payload = (
            f"{self.provider}\x1f{self.model}\x1f{self.version}\x1f{self.dimension}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "embedding_provider": self.provider,
            "embedding_model": self.model,
            "embedding_version": self.version,
            "embedding_dimension": self.dimension,
            "embedding_identity": self.identity,
        }


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieval hit — content + provenance + score, never anonymous."""

    chunk: KnowledgeChunk
    score: float
    rank: int

    @property
    def provenance(self) -> Provenance:
        return self.chunk.provenance

    def citation(self) -> str:
        return self.chunk.provenance.citation()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score": round(self.score, 6),
            "citation": self.citation(),
            "chunk": self.chunk.to_dict(),
        }


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class KnowledgeIndex:
    def __init__(
        self,
        provider: EmbeddingProvider,
        model_id: EmbeddingModelId,
        *,
        workspace_id: str | None = None,
    ) -> None:
        self._provider = provider
        self._model_id = model_id
        self._workspace_id = workspace_id
        self._vectors: dict[str, tuple[float, ...]] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}

    # -- identity ----------------------------------------------------

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._model_id

    @property
    def index_identity(self) -> str:
        base = self._model_id.identity
        if self._workspace_id:
            base = hashlib.sha256(
                f"{base}\x1f{self._workspace_id}".encode("utf-8")
            ).hexdigest()[:16]
        return base

    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._chunks),
            "index_identity": self.index_identity,
            "workspace_id": self._workspace_id,
            **self._model_id.to_dict(),
            "by_chunk_type": self._by_type(),
            "by_source": sorted(
                {c.provenance.source_id for c in self._chunks.values()}
            ),
        }

    def _by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self._chunks.values():
            out[c.chunk_type.value] = out.get(c.chunk_type.value, 0) + 1
        return dict(sorted(out.items()))

    # -- write -----------------------------------------------------

    def add(self, chunks: Iterable[KnowledgeChunk]) -> int:
        items = list(chunks)
        for c in items:
            try:
                c.provenance.validate_complete()
            except ProvenanceError as exc:
                raise IndexError_(
                    f"refusing to index chunk {c.chunk_id}: {exc}"
                ) from exc
            if self._workspace_id and c.metadata.get("workspace_id") not in (
                None,
                self._workspace_id,
            ):
                raise EmbeddingIdentityError(
                    f"chunk {c.chunk_id} belongs to workspace "
                    f"{c.metadata.get('workspace_id')}, not {self._workspace_id}"
                )
        texts = [c.content for c in items]
        vectors = self._provider.embed_batch(texts) if texts else []
        for c, vec in zip(items, vectors):
            if len(vec) != self._model_id.dimension:
                raise EmbeddingIdentityError(
                    f"embedding for {c.chunk_id} has dimension {len(vec)}, "
                    f"index expects {self._model_id.dimension}"
                )
            self._vectors[c.chunk_id] = tuple(vec)
            self._chunks[c.chunk_id] = c
        return len(items)

    def delete(self, chunk_ids: Iterable[str]) -> int:
        n = 0
        for cid in chunk_ids:
            if cid in self._chunks:
                del self._chunks[cid]
                del self._vectors[cid]
                n += 1
        return n

    def contains(self, chunk_id: str) -> bool:
        return chunk_id in self._chunks

    def size(self) -> int:
        return len(self._chunks)

    # -- read -----------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        if not query or not query.strip():
            raise IndexError_("query must be non-empty")
        if top_k <= 0:
            raise IndexError_("top_k must be positive")
        qvec = tuple(self._provider.embed(query))
        if len(qvec) != self._model_id.dimension:
            raise EmbeddingIdentityError(
                "query embedding dimension does not match the index"
            )
        cand = [(cid, c) for cid, c in self._chunks.items() if _matches(c, filters)]
        scored = [(self._score(qvec, cid), cid, c) for cid, c in cand]
        # deterministic tie-break: score desc, then chunk_id asc
        scored.sort(key=lambda t: (-t[0], t[1]))
        out: list[RetrievedChunk] = []
        for rank, (score, _cid, chunk) in enumerate(scored[:top_k], start=1):
            out.append(RetrievedChunk(chunk=chunk, score=score, rank=rank))
        return out

    def _score(self, qvec: tuple[float, ...], chunk_id: str) -> float:
        return _cosine(qvec, self._vectors[chunk_id])


_FILTERABLE = {
    "source_id",
    "source_type",
    "chunk_type",
    "paragraph",
    "section",
    "artifact_version",
    "rule_id",
    "risk_id",
    "strategy_id",
    "dependency_type",
    "severity",
    "java_class",
    "java_method",
    "workspace_id",
}


def _matches(chunk: KnowledgeChunk, filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    md = chunk.index_metadata()
    for key, want in filters.items():
        if key not in _FILTERABLE:
            raise IndexError_(f"unknown retrieval filter {key!r}")
        have = md.get(key)
        if isinstance(want, (list, tuple, set)):
            if have not in want:
                return False
        elif have != want:
            return False
    return True
