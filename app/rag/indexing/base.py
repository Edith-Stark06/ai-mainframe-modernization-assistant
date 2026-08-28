from abc import ABC, abstractmethod
from typing import Sequence
from app.rag.embeddings.models import Embedding


class VectorIndex(ABC):
    """
    Abstract interface for a vector index.
    """

    @abstractmethod
    def add(self, embeddings: Sequence[Embedding]) -> None:
        """Add or update embeddings in the index."""
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
