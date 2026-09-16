from typing import Mapping

from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.indexing.base import VectorIndex
from app.rag.retrieval.models import RetrievalResult


class RetrievalService:
    """
    Provider-independent service for searching indexed knowledge chunks
    using natural language queries.
    """

    def __init__(self, provider: EmbeddingProvider, index: VectorIndex) -> None:
        self.provider = provider
        self.index = index

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Mapping[str, str | int | float | bool] | None = None,
    ) -> list[RetrievalResult]:
        """
        Searches the index for chunks most relevant to the text query.
        Returns up to top_k deterministically ranked results.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or whitespace-only")

        if top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        # Determine the allowed filter dict
        valid_filter: dict[str, str | int | float | bool] | None = None
        if filter_metadata is not None:
            valid_filter = dict(filter_metadata)

        query_vector = self.provider.embed(query)

        # Let the underlying index raise exceptions if there are dimension mismatches
        return self.index.search(
            query_vector=query_vector,
            top_k=top_k,
            filter_metadata=valid_filter,
        )
