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
