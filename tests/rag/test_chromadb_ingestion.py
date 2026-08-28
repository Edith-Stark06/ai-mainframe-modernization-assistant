import pytest
import tempfile
from typing import Generator

from app.rag.indexing.chroma import ChromaIndex
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


def test_chroma_index_basic_ingestion(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 3)
    emb = Embedding(chunk_id="c1", vector=(0.1, 0.2, 0.3), dimension=3)

    index.add([emb])

    assert index.size() == 1
    assert index.contains("c1")
    assert not index.contains("c2")

    retrieved = index.get("c1")
    assert retrieved is not None
    assert retrieved.vector == pytest.approx((0.1, 0.2, 0.3), rel=1e-5)


def test_chroma_index_with_chunks(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 2)
    chunk = _create_chunk(
        "c1", content="hello", metadata={"source": "test.txt", "flag": True}
    )
    emb = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2, model="test-model")

    index.add([emb], [chunk])

    assert index.size() == 1
    retrieved = index.get("c1")
    assert retrieved is not None
    assert retrieved.model == "test-model"


def test_chroma_index_persistence(temp_db_path: str) -> None:
    index1 = ChromaIndex(temp_db_path, "test_col", 2)
    emb = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)
    index1.add([emb])

    # Recreate index on same path
    index2 = ChromaIndex(temp_db_path, "test_col", 2)
    assert index2.size() == 1
    assert index2.contains("c1")


def test_chroma_index_collection_isolation(temp_db_path: str) -> None:
    index_a = ChromaIndex(temp_db_path, "col_a", 2)
    index_b = ChromaIndex(temp_db_path, "col_b", 2)

    emb_a = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)
    emb_b = Embedding(chunk_id="c2", vector=(0.3, 0.4), dimension=2)

    index_a.add([emb_a])
    index_b.add([emb_b])

    assert index_a.size() == 1
    assert index_b.size() == 1

    assert index_a.contains("c1")
    assert not index_a.contains("c2")

    assert index_b.contains("c2")
    assert not index_b.contains("c1")


def test_chroma_index_idempotent_upsert(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 2)
    emb1 = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)
    index.add([emb1])

    emb2 = Embedding(chunk_id="c1", vector=(0.9, 0.8), dimension=2)
    index.add([emb2])

    assert index.size() == 1
    retrieved = index.get("c1")
    assert retrieved is not None
    assert retrieved.vector == pytest.approx((0.9, 0.8), rel=1e-5)


def test_chroma_index_invalid_dimension(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 3)
    emb = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)

    with pytest.raises(ValueError, match="Dimension mismatch"):
        index.add([emb])


def test_chroma_index_invalid_metadata(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 2)
    chunk = _create_chunk("c1", metadata={"bad": [1, 2, 3]})  # type: ignore
    emb = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)

    with pytest.raises(ValueError, match="Unsupported metadata type"):
        index.add([emb], [chunk])


def test_chroma_index_length_mismatch(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 2)
    chunk = _create_chunk("c1")
    emb1 = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)
    emb2 = Embedding(chunk_id="c2", vector=(0.3, 0.4), dimension=2)

    with pytest.raises(ValueError, match="must have the same length"):
        index.add([emb1, emb2], [chunk])


def test_chroma_index_chunk_id_mismatch(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 2)
    chunk = _create_chunk("c2")
    emb = Embedding(chunk_id="c1", vector=(0.1, 0.2), dimension=2)

    with pytest.raises(ValueError, match="chunk_id mismatch"):
        index.add([emb], [chunk])


def test_chroma_index_empty_add(temp_db_path: str) -> None:
    index = ChromaIndex(temp_db_path, "test_col", 2)
    index.add([])
    assert index.size() == 0
