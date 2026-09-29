from abc import ABC, abstractmethod
from typing import Sequence
import hashlib

from loguru import logger


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


class SentenceTransformerProvider(EmbeddingProvider):
    """
    A real, local embedding provider backed by the ``sentence-transformers``
    library (already a pinned project dependency -- see ``pyproject.toml``).
    Runs entirely on-device: after the model weights are first downloaded
    and cached, no network call is made per embedding.

    The default model, ``all-MiniLM-L6-v2``, produces 384-dimensional
    vectors -- matching the dimension every ``ChromaIndex`` in this
    codebase is already constructed with (see
    ``app/api/routers/chat.py``'s ``get_rag_orchestrator``), so switching
    from :class:`DeterministicFakeProvider` requires no index migration.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        # Imported lazily: importing this module must not force-load
        # sentence-transformers/torch for callers that only ever use
        # DeterministicFakeProvider (most tests).
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        logger.info(
            "SentenceTransformerProvider: loading model '{}' (first run "
            "downloads and caches it locally).",
            model_name,
        )
        self._model = SentenceTransformer(model_name)
        dimension = self._model.get_embedding_dimension()
        if dimension is None:
            raise ValueError(
                f"Model '{model_name}' does not report an embedding dimension."
            )
        self.dimension = dimension

    def embed(self, text: str) -> tuple[float, ...]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        vectors = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [tuple(float(x) for x in vector) for vector in vectors]
