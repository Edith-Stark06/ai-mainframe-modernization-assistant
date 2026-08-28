import pytest

from app.rag.retrieval.service import RetrievalService
from app.rag.indexing.memory import InMemoryIndex
from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.embeddings.models import Embedding
from app.rag.models import KnowledgeChunk


def _create_chunk(
    chunk_id: str,
    doc_id: str = "d1",
    content: str = "text",
    index: int = 0,
    metadata: dict | None = None,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=chunk_id,
        document_id=doc_id,
        content=content,
        chunk_index=index,
        metadata=metadata or {},
    )


@pytest.fixture
def memory_index() -> InMemoryIndex:
    return InMemoryIndex(expected_dimension=4)


@pytest.fixture
def fake_provider() -> DeterministicFakeProvider:
    return DeterministicFakeProvider(dimension=4)


def test_retrieval_service_basic(
    memory_index: InMemoryIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, memory_index)

    # Ingest some chunks
    chunks = [
        _create_chunk("c1", content="hello world"),
        _create_chunk("c2", content="foo bar baz"),
    ]
    # We'll compute their deterministic vectors just for storing them
    vectors = fake_provider.embed_batch([c.content for c in chunks])
    embeddings = [
        Embedding(chunk_id=c.id, vector=v, dimension=4) for c, v in zip(chunks, vectors)
    ]
    memory_index.add(embeddings, chunks)

    results = service.search("hello world", top_k=5)

    # Since "hello world" hashes to the exact same vector as c1's content,
    # c1 should have distance 0.
    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    assert results[0].score == pytest.approx(0.0, abs=1e-5)
    assert results[1].chunk_id == "c2"


def test_retrieval_service_top_k(
    memory_index: InMemoryIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, memory_index)
    chunks = [_create_chunk(f"c{i}") for i in range(10)]
    vectors = fake_provider.embed_batch([f"text{i}" for i in range(10)])
    embeddings = [
        Embedding(chunk_id=c.id, vector=v, dimension=4) for c, v in zip(chunks, vectors)
    ]
    memory_index.add(embeddings, chunks)

    results = service.search("query", top_k=3)
    assert len(results) == 3


def test_retrieval_service_empty_query(
    memory_index: InMemoryIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, memory_index)
    with pytest.raises(ValueError, match="Query cannot be empty"):
        service.search("   ")


def test_retrieval_service_invalid_top_k(
    memory_index: InMemoryIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, memory_index)
    with pytest.raises(ValueError, match="positive integer"):
        service.search("query", top_k=0)


def test_retrieval_service_tie_breaking(
    memory_index: InMemoryIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, memory_index)

    # Force identical vectors for different chunks
    v = (0.5, 0.5, 0.5, 0.5)
    chunks = [
        _create_chunk("c2", doc_id="d1", index=0),
        _create_chunk("c1", doc_id="d1", index=1),
        _create_chunk("c3", doc_id="d2", index=0),
    ]
    embeddings = [Embedding(chunk_id=c.id, vector=v, dimension=4) for c in chunks]
    memory_index.add(embeddings, chunks)

    # Search with a vector that gives same distance to all
    results = service.search("any query", top_k=3)

    # Tie breaking order: score, doc_id, chunk_index, chunk_id
    assert results[0].document_id == "d1"
    assert results[0].chunk_index == 0
    assert results[0].chunk_id == "c2"

    assert results[1].document_id == "d1"
    assert results[1].chunk_index == 1
    assert results[1].chunk_id == "c1"

    assert results[2].document_id == "d2"


def test_retrieval_service_metadata_filter(
    memory_index: InMemoryIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, memory_index)
    chunks = [
        _create_chunk("c1", metadata={"type": "code"}),
        _create_chunk("c2", metadata={"type": "doc"}),
    ]
    vectors = fake_provider.embed_batch([f"text{i}" for i in range(2)])
    embeddings = [
        Embedding(chunk_id=c.id, vector=v, dimension=4) for c, v in zip(chunks, vectors)
    ]
    memory_index.add(embeddings, chunks)

    results = service.search("query", filter_metadata={"type": "doc"})
    assert len(results) == 1
    assert results[0].chunk_id == "c2"
