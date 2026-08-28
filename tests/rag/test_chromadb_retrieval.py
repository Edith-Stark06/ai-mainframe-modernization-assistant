import pytest
import tempfile
from typing import Generator

from app.rag.retrieval.service import RetrievalService
from app.rag.indexing.chroma import ChromaIndex
from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.embeddings.models import Embedding
from app.rag.models import KnowledgeChunk


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        yield td


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
def chroma_index(temp_db_path: str) -> ChromaIndex:
    return ChromaIndex(temp_db_path, "test_collection", 4)


@pytest.fixture
def fake_provider() -> DeterministicFakeProvider:
    return DeterministicFakeProvider(dimension=4)


def test_chromadb_retrieval_service_basic(
    chroma_index: ChromaIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, chroma_index)

    chunks = [
        _create_chunk("c1", content="hello world"),
        _create_chunk("c2", content="foo bar baz"),
    ]
    vectors = fake_provider.embed_batch([c.content for c in chunks])
    embeddings = [
        Embedding(chunk_id=c.id, vector=v, dimension=4) for c, v in zip(chunks, vectors)
    ]
    chroma_index.add(embeddings, chunks)

    results = service.search("hello world", top_k=2)

    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    # Distance in Chroma for identical vectors should be 0 or very small
    assert results[0].score == pytest.approx(0.0, abs=1e-5)
    assert results[1].chunk_id == "c2"


def test_chromadb_retrieval_metadata_filter(
    chroma_index: ChromaIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, chroma_index)
    chunks = [
        _create_chunk("c1", metadata={"type": "code"}),
        _create_chunk("c2", metadata={"type": "doc"}),
    ]
    vectors = fake_provider.embed_batch([c.content for c in chunks])
    embeddings = [
        Embedding(chunk_id=c.id, vector=v, dimension=4) for c, v in zip(chunks, vectors)
    ]
    chroma_index.add(embeddings, chunks)

    results = service.search("query", filter_metadata={"type": "doc"})
    assert len(results) == 1
    assert results[0].chunk_id == "c2"
    assert results[0].metadata.get("type") == "doc"


def test_chromadb_retrieval_tie_breaking(
    chroma_index: ChromaIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, chroma_index)

    # Force identical vectors
    v = (0.5, 0.5, 0.5, 0.5)
    chunks = [
        _create_chunk("c2", doc_id="d1", index=0),
        _create_chunk("c1", doc_id="d1", index=1),
        _create_chunk("c3", doc_id="d2", index=0),
    ]
    embeddings = [Embedding(chunk_id=c.id, vector=v, dimension=4) for c in chunks]
    chroma_index.add(embeddings, chunks)

    results = service.search("any query", top_k=3)

    # Check deterministic ordering: score, doc_id, chunk_index, chunk_id
    assert results[0].document_id == "d1"
    assert results[0].chunk_index == 0
    assert results[0].chunk_id == "c2"

    assert results[1].document_id == "d1"
    assert results[1].chunk_index == 1
    assert results[1].chunk_id == "c1"

    assert results[2].document_id == "d2"


def test_chromadb_retrieval_empty(
    chroma_index: ChromaIndex, fake_provider: DeterministicFakeProvider
) -> None:
    service = RetrievalService(fake_provider, chroma_index)
    results = service.search("query")
    assert len(results) == 0
