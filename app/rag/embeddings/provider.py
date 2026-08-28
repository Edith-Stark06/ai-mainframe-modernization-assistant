from abc import ABC, abstractmethod
from typing import Sequence
import hashlib


class EmbeddingProvider(ABC):
    """
    Abstract interface for embedding text.
    """

    @abstractmethod
    def embed(self, text: str) -> tuple[float, ...]:
        """Embeds a single string and returns its vector representation."""
        pass

    @abstractmethod
    def embed_batch(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        """Embeds multiple strings and returns their vector representations in order."""
        pass


class DeterministicFakeProvider(EmbeddingProvider):
    """
    A deterministic fake provider for tests.
    Generates deterministic vectors using cryptographic hashing (SHA-256).
    """

    def __init__(self, dimension: int, model_name: str | None = None) -> None:
        if dimension <= 0:
            raise ValueError("Dimension must be positive")
        self.dimension = dimension
        self.model_name = model_name

    def embed(self, text: str) -> tuple[float, ...]:
        if not text or not text.strip():
            # Generate deterministic empty-ish vector
            return tuple(0.0 for _ in range(self.dimension))

        vector: list[float] = []
        current_hash = text.encode("utf-8")

        while len(vector) < self.dimension:
            h = hashlib.sha256(current_hash)
            digest = h.digest()
            # Convert bytes to floats [-1.0, 1.0]
            for b in digest:
                if len(vector) >= self.dimension:
                    break
                val = (b / 127.5) - 1.0
                vector.append(val)
            current_hash = digest

        return tuple(vector)

    def embed_batch(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]
