import pytest
from app.rag.embeddings.models import Embedding
from app.rag.indexing.memory import InMemoryIndex
from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.embeddings.service import EmbeddingService
from app.rag.models import KnowledgeChunk


def test_in_memory_index_add_and_get() -> None:
    index = InMemoryIndex(expected_dimension=3)
    emb1 = Embedding(chunk_id="c1", vector=(0.1, 0.2, 0.3), dimension=3)
    emb2 = Embedding(chunk_id="c2", vector=(0.4, 0.5, 0.6), dimension=3)

    index.add([emb1, emb2])

    assert index.size() == 2
    assert index.contains("c1")
    assert index.contains("c2")
    assert not index.contains("c3")

    retrieved1 = index.get("c1")
    assert retrieved1 is not None
    assert retrieved1.vector == (0.1, 0.2, 0.3)

    assert index.get("c3") is None


def test_in_memory_index_dimension_mismatch() -> None:
    index = InMemoryIndex(expected_dimension=3)
    emb = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)

    with pytest.raises(ValueError, match="Dimension mismatch"):
        index.add([emb])


def test_in_memory_index_upsert() -> None:
    index = InMemoryIndex(expected_dimension=2)
    emb1 = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)
    index.add([emb1])

    emb2 = Embedding(chunk_id="c1", vector=(0.9, 0.8), dimension=2)
    index.add([emb2])

    assert index.size() == 1
    assert index.get("c1").vector == (0.9, 0.8)  # type: ignore


def test_in_memory_index_invalid_dimension_init() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        InMemoryIndex(expected_dimension=0)


def test_e2e_chunk_to_index() -> None:
    # 1. Provide chunks
    chunks = [
        KnowledgeChunk(
            id="c1", document_id="d1", content="alpha", chunk_index=0, metadata={}
        ),
        KnowledgeChunk(
            id="c2", document_id="d1", content="beta", chunk_index=1, metadata={}
        ),
    ]

    # 2. Embedding Service + Provider
    provider = DeterministicFakeProvider(dimension=4, model_name="e2e-model")
    service = EmbeddingService(provider)
    embeddings = service.embed_chunks(chunks)

    assert len(embeddings) == 2
    assert embeddings[0].model == "e2e-model"

    # 3. Index
    index = InMemoryIndex(expected_dimension=4)
    index.add(embeddings)

    assert index.size() == 2
    assert index.contains("c1")
    assert index.contains("c2")

    retrieved = index.get("c1")
    assert retrieved is not None
    assert retrieved.vector == provider.embed("alpha")
