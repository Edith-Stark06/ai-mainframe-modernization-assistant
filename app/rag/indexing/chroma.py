import pathlib
from typing import Sequence, Any
import chromadb
from chromadb.api.models.Collection import Collection

from app.rag.indexing.base import VectorIndex
from app.rag.embeddings.models import Embedding
from app.rag.models import KnowledgeChunk
from app.rag.retrieval.models import RetrievalResult


class ChromaIndex(VectorIndex):
    """
    A persistent ChromaDB-backed implementation of VectorIndex.
    """

    def __init__(
        self,
        persist_directory: str | pathlib.Path,
        collection_name: str,
        expected_dimension: int,
    ) -> None:
        if expected_dimension <= 0:
            raise ValueError("expected_dimension must be positive")

        if not collection_name or len(collection_name) < 3 or len(collection_name) > 63:
            raise ValueError("collection_name must be between 3 and 63 characters")

        self.expected_dimension = expected_dimension
        self.persist_directory = str(persist_directory)
        self.collection_name = collection_name

        self._client = chromadb.PersistentClient(path=self.persist_directory)
        self._collection: Collection = self._client.get_or_create_collection(
            name=self.collection_name
        )

    def _validate_metadata_value(self, value: Any) -> Any:
        """Ensures metadata values are JSON-compatible scalar types that ChromaDB supports."""
        if isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError(
            f"Unsupported metadata type for ChromaDB: {type(value).__name__}"
        )

    def add(
        self,
        embeddings: Sequence[Embedding],
        chunks: Sequence[KnowledgeChunk] | None = None,
    ) -> None:
        if not embeddings:
            return

        if chunks is not None:
            if len(embeddings) != len(chunks):
                raise ValueError("embeddings and chunks must have the same length")

        ids = []
        vectors = []
        documents = []
        metadatas = []

        for i, emb in enumerate(embeddings):
            if emb.dimension != self.expected_dimension:
                raise ValueError(
                    f"Dimension mismatch: expected {self.expected_dimension}, got {emb.dimension}"
                )

            ids.append(emb.chunk_id)
            vectors.append(list(emb.vector))

            if chunks is not None:
                chunk = chunks[i]
                if chunk.id != emb.chunk_id:
                    raise ValueError(f"chunk_id mismatch: {emb.chunk_id} != {chunk.id}")

                documents.append(chunk.content)

                metadata: dict[str, Any] = {}
                metadata["document_id"] = chunk.document_id
                metadata["chunk_index"] = chunk.chunk_index

                for k, v in chunk.metadata.items():
                    if v is not None:
                        metadata[k] = self._validate_metadata_value(v)

                # Add embedding model info if available
                if emb.model is not None:
                    metadata["embedding_model"] = emb.model

                metadatas.append(metadata)

        kwargs: dict[str, Any] = {
            "ids": ids,
            "embeddings": vectors,
        }

        if chunks is not None:
            kwargs["documents"] = documents
            kwargs["metadatas"] = metadatas

        self._collection.upsert(**kwargs)

    def contains(self, chunk_id: str) -> bool:
        result = self._collection.get(ids=[chunk_id], include=[])
        return len(result["ids"]) > 0

    def get(self, chunk_id: str) -> Embedding | None:
        result = self._collection.get(
            ids=[chunk_id], include=["embeddings", "metadatas"]
        )
        if not result["ids"]:
            return None

        # mypy requires checks when indexing lists returned by ChromaDB since they are Optional
        embeddings_list = result.get("embeddings")
        if embeddings_list is None or len(embeddings_list) == 0:
            return None

        vector = embeddings_list[0]
        vector_tuple = tuple(float(x) for x in vector)

        metadatas_list = result.get("metadatas")
        model = None
        if metadatas_list and metadatas_list[0]:
            model_val = metadatas_list[0].get("embedding_model")
            if isinstance(model_val, str):
                model = model_val

        return Embedding(
            chunk_id=chunk_id,
            vector=vector_tuple,
            dimension=len(vector_tuple),
            model=model,
        )

    def size(self) -> int:
        return self._collection.count()

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

        # ChromaDB query syntax uses "where" for metadata filtering
        kwargs: dict[str, Any] = {
            "query_embeddings": [list(query_vector)],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_metadata:
            # For simple key-value match
            kwargs["where"] = filter_metadata

        # mypy will complain if we don't handle Optional properly
        # Since we might query an empty DB, chromadb returns empty lists
        result = self._collection.query(**kwargs)

        ids_list = result.get("ids")
        if not ids_list or not ids_list[0]:
            return []

        distances_list = result.get("distances")
        if not distances_list or not distances_list[0]:
            return []

        documents_list = result.get("documents")
        if not documents_list or not documents_list[0]:
            return []

        metadatas_list = result.get("metadatas")
        if not metadatas_list or not metadatas_list[0]:
            return []

        # They are returned as list of lists (one per query)
        batch_ids = ids_list[0]
        batch_distances = distances_list[0]
        batch_documents = documents_list[0]
        batch_metadatas = metadatas_list[0]

        parsed_results: list[RetrievalResult] = []

        for i in range(len(batch_ids)):
            chunk_id = batch_ids[i]
            dist = float(batch_distances[i])
            doc_content = batch_documents[i]
            meta = batch_metadatas[i] or {}

            # Extract reserved metadata
            doc_id = str(meta.get("document_id", ""))
            chunk_idx_raw = meta.get("chunk_index", 0)
            chunk_idx = (
                int(chunk_idx_raw)
                if isinstance(chunk_idx_raw, (int, float, str))
                else 0
            )

            # Remove them from the chunk metadata mapping to avoid duplication?
            # Or leave them, but chunk.metadata should just be the dictionary.
            # We'll put all meta in metadata for simplicity, since it's an ImmutableDict.
            # But the chunk requires them explicitly for initialization.
            parsed_results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    content=doc_content,
                    chunk_index=chunk_idx,
                    metadata=meta,
                    score=dist,
                )
            )

        # Ensure deterministic ordering: distance (asc), doc_id, chunk_index, chunk_id
        parsed_results.sort(
            key=lambda r: (r.score, r.document_id, r.chunk_index, r.chunk_id)
        )

        return parsed_results
