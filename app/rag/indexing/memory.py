from typing import Sequence

from app.rag.indexing.base import VectorIndex
from app.rag.embeddings.models import Embedding
from app.rag.models import KnowledgeChunk
from app.rag.retrieval.models import RetrievalResult


class InMemoryIndex(VectorIndex):
    """
    A simple in-memory implementation of VectorIndex for tests.
    """

    def __init__(self, expected_dimension: int) -> None:
        if expected_dimension <= 0:
            raise ValueError("expected_dimension must be positive")
        self.expected_dimension = expected_dimension
        self._storage: dict[str, Embedding] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}

    def add(
        self,
        embeddings: Sequence[Embedding],
        chunks: Sequence[KnowledgeChunk] | None = None,
    ) -> None:
        if chunks is not None:
            if len(embeddings) != len(chunks):
                raise ValueError("embeddings and chunks must have the same length")
            for emb, chunk in zip(embeddings, chunks):
                if emb.chunk_id != chunk.id:
                    raise ValueError(f"chunk_id mismatch: {emb.chunk_id} != {chunk.id}")

        for i, emb in enumerate(embeddings):
            if emb.dimension != self.expected_dimension:
                raise ValueError(
                    f"Dimension mismatch: expected {self.expected_dimension}, got {emb.dimension}"
                )
            self._storage[emb.chunk_id] = emb
            if chunks is not None:
                self._chunks[emb.chunk_id] = chunks[i]
            elif emb.chunk_id not in self._chunks:
                # If chunk wasn't provided and not in storage, create a dummy one for testing?
                # Or just do nothing, but search might fail if chunks are missing.
                pass

    def contains(self, chunk_id: str) -> bool:
        return chunk_id in self._storage

    def get(self, chunk_id: str) -> Embedding | None:
        return self._storage.get(chunk_id)

    def size(self) -> int:
        return len(self._storage)

    def search(
        self,
        query_vector: tuple[float, ...],
        top_k: int,
        filter_metadata: dict[str, str | int | float | bool] | None = None,
    ) -> list[RetrievalResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if len(query_vector) != self.expected_dimension:
            raise ValueError("query_vector dimension mismatch")

        results: list[RetrievalResult] = []

        for chunk_id, emb in self._storage.items():
            chunk = self._chunks.get(chunk_id)
            if not chunk:
                continue

            if filter_metadata:
                match = True
                for k, v in filter_metadata.items():
                    if chunk.metadata.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            # L2 squared distance
            dist = sum((a - b) ** 2 for a, b in zip(query_vector, emb.vector))

            results.append(
                RetrievalResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    metadata=chunk.metadata,
                    score=dist,
                )
            )

        # Sort: distance (asc), then document_id (asc), chunk_index (asc), chunk_id (asc)
        results.sort(key=lambda r: (r.score, r.document_id, r.chunk_index, r.chunk_id))

        return results[:top_k]
