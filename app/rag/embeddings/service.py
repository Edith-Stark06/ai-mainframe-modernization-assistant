from typing import Sequence
from app.rag.models import KnowledgeChunk
from app.rag.embeddings.models import Embedding
from app.rag.embeddings.provider import EmbeddingProvider


class EmbeddingService:
    """
    Coordinates chunk processing by converting KnowledgeChunk objects into
    searchable vector representations using an EmbeddingProvider.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def embed_chunks(self, chunks: Sequence[KnowledgeChunk]) -> list[Embedding]:
        if not chunks:
            return []

        # Validate duplicate IDs
        seen = set()
        for chunk in chunks:
            if chunk.id in seen:
                raise ValueError(f"Duplicate chunk ID found: {chunk.id}")
            seen.add(chunk.id)

        texts = [chunk.content for chunk in chunks]
        vectors = self.provider.embed_batch(texts)

        # Determine the model name if the provider exposes it
        model_name = getattr(self.provider, "model_name", None)

        embeddings = []
        for chunk, vector in zip(chunks, vectors):
            embeddings.append(
                Embedding(
                    chunk_id=chunk.id,
                    vector=vector,
                    dimension=len(vector),
                    model=model_name,
                )
            )

        return embeddings
