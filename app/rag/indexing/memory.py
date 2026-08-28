from typing import Sequence
from app.rag.indexing.base import VectorIndex
from app.rag.embeddings.models import Embedding
from app.rag.models import KnowledgeChunk


class InMemoryIndex(VectorIndex):
    """
    A simple in-memory implementation of VectorIndex for tests.
    """

    def __init__(self, expected_dimension: int) -> None:
        if expected_dimension <= 0:
            raise ValueError("expected_dimension must be positive")
        self.expected_dimension = expected_dimension
        self._storage: dict[str, Embedding] = {}

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

        for emb in embeddings:
            if emb.dimension != self.expected_dimension:
                raise ValueError(
                    f"Dimension mismatch: expected {self.expected_dimension}, got {emb.dimension}"
                )
            self._storage[emb.chunk_id] = emb

    def contains(self, chunk_id: str) -> bool:
        return chunk_id in self._storage

    def get(self, chunk_id: str) -> Embedding | None:
        return self._storage.get(chunk_id)

    def size(self) -> int:
        return len(self._storage)
