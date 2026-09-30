from abc import ABC, abstractmethod
from typing import Sequence
from app.rag.embeddings.models import Embedding
from app.rag.models import KnowledgeChunk
from app.rag.retrieval.models import RetrievalResult


class VectorIndex(ABC):
    """
    Abstract interface for a vector index.
    """

    @abstractmethod
    def add(
        self,
        embeddings: Sequence[Embedding],
        chunks: Sequence[KnowledgeChunk] | None = None,
    ) -> None:
        """Add or update embeddings in the index. Optionally include chunks for persistent storage."""
        pass

    @abstractmethod
    def contains(self, chunk_id: str) -> bool:
        """Check if a chunk_id exists in the index."""
        pass

    @abstractmethod
    def get(self, chunk_id: str) -> Embedding | None:
        """Retrieve an embedding by its chunk_id."""
        pass

    @abstractmethod
    def size(self) -> int:
        """Return the number of embeddings in the index."""
        pass

    @abstractmethod
    def search(
        self,
        query_vector: tuple[float, ...],
        top_k: int,
        filter_metadata: dict[str, str | int | float | bool] | None = None,
    ) -> list["RetrievalResult"]:
        """Search the index for chunks closest to the query_vector."""
        pass

    def list_chunks(
        self,
        filter_metadata: dict[str, str | int | float | bool] | None = None,
    ) -> list["RetrievalResult"]:
        """
        Return every stored chunk matching *filter_metadata* (``score`` is
        ``0.0``: no query is involved), in a deterministic order.

        Used by lexical/hybrid retrieval, which needs the chunk text rather
        than a vector neighbourhood. Not abstract: an index that cannot
        enumerate its chunks raises ``NotImplementedError`` and callers fall
        back to vector-only search.
        """
        raise NotImplementedError

    def delete(
        self,
        filter_metadata: dict[str, str | int | float | bool],
    ) -> int:
        """
        Remove every chunk matching *filter_metadata* and return how many
        were removed. A non-empty filter is required (deleting everything
        must be a deliberate, separate act). Raises ``NotImplementedError``
        for an index that cannot delete.
        """
        raise NotImplementedError
