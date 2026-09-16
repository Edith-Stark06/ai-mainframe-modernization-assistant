import pytest
import json
from app.rag.embeddings.models import Embedding
from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.embeddings.service import EmbeddingService
from app.rag.models import KnowledgeChunk


def test_embedding_valid() -> None:
    emb = Embedding(
        chunk_id="chunk1", vector=(0.1, 0.2, 0.3), dimension=3, model="fake-model"
    )
    assert emb.chunk_id == "chunk1"
    assert emb.dimension == 3
    assert emb.vector == (0.1, 0.2, 0.3)


def test_embedding_empty_chunk_id() -> None:
    with pytest.raises(ValueError, match="chunk_id cannot be empty"):
        Embedding(chunk_id="", vector=(0.1,), dimension=1)


def test_embedding_empty_vector() -> None:
    with pytest.raises(ValueError, match="vector cannot be empty"):
        Embedding(chunk_id="c1", vector=(), dimension=0)


def test_embedding_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match dimension"):
        Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=3)


def test_embedding_nan_rejection() -> None:
    with pytest.raises(ValueError, match="finite numbers"):
        Embedding(chunk_id="c1", vector=(0.1, float("nan")), dimension=2)


def test_embedding_infinity_rejection() -> None:
    with pytest.raises(ValueError, match="finite numbers"):
        Embedding(chunk_id="c1", vector=(0.1, float("inf")), dimension=2)


def test_embedding_non_numeric_rejection() -> None:
    with pytest.raises(ValueError, match="finite numbers"):
        Embedding(chunk_id="c1", vector=(0.1, "0.2"), dimension=2)  # type: ignore


def test_embedding_to_dict_serialization() -> None:
    emb = Embedding(
        chunk_id="chunk1", vector=(0.1, 0.2, 0.3), dimension=3, model="test-model"
    )
    data = emb.to_dict()
    serialized = json.dumps(data)
    assert "chunk1" in serialized
    assert "test-model" in serialized

    loaded = json.loads(serialized)
    assert loaded["vector"] == [0.1, 0.2, 0.3]
    assert loaded["dimension"] == 3


def test_fake_provider_determinism() -> None:
    provider = DeterministicFakeProvider(dimension=5, model_name="fake")
    vec1 = provider.embed("hello world")
    vec2 = provider.embed("hello world")
    assert vec1 == vec2
    assert len(vec1) == 5
    assert all(-1.0 <= v <= 1.0 for v in vec1)


def test_fake_provider_batch() -> None:
    provider = DeterministicFakeProvider(dimension=4)
    texts = ["a", "b", "c"]
    vectors = provider.embed_batch(texts)

    assert len(vectors) == 3
    assert vectors[0] == provider.embed("a")
    assert vectors[1] == provider.embed("b")
    assert vectors[2] == provider.embed("c")


def test_fake_provider_empty_input() -> None:
    provider = DeterministicFakeProvider(dimension=3)
    vec = provider.embed("")
    assert vec == (0.0, 0.0, 0.0)


def test_embedding_service_processing() -> None:
    provider = DeterministicFakeProvider(dimension=2, model_name="test-model")
    service = EmbeddingService(provider)

    chunks = [
        KnowledgeChunk(
            id="c1", document_id="d1", content="hello", chunk_index=0, metadata={}
        ),
        KnowledgeChunk(
            id="c2", document_id="d1", content="world", chunk_index=1, metadata={}
        ),
    ]

    embeddings = service.embed_chunks(chunks)
    assert len(embeddings) == 2
    assert embeddings[0].chunk_id == "c1"
    assert embeddings[0].dimension == 2
    assert embeddings[0].model == "test-model"
    assert embeddings[0].vector == provider.embed("hello")

    assert embeddings[1].chunk_id == "c2"
    assert embeddings[1].vector == provider.embed("world")


def test_embedding_service_duplicate_ids() -> None:
    provider = DeterministicFakeProvider(dimension=2)
    service = EmbeddingService(provider)

    chunks = [
        KnowledgeChunk(
            id="c1", document_id="d1", content="a", chunk_index=0, metadata={}
        ),
        KnowledgeChunk(
            id="c1", document_id="d1", content="b", chunk_index=1, metadata={}
        ),
    ]

    with pytest.raises(ValueError, match="Duplicate chunk ID"):
        service.embed_chunks(chunks)


def test_embedding_service_empty() -> None:
    provider = DeterministicFakeProvider(dimension=2)
    service = EmbeddingService(provider)
    assert service.embed_chunks([]) == []
