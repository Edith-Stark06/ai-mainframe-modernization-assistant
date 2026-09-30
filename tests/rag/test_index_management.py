"""VectorIndex.list_chunks / delete on the in-memory and Chroma indexes."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.embeddings.service import EmbeddingService
from app.rag.indexing.base import VectorIndex
from app.rag.indexing.chroma import ChromaIndex
from app.rag.indexing.memory import InMemoryIndex
from app.rag.models import KnowledgeChunk

DIM = 32
PROVIDER = DeterministicFakeProvider(dimension=DIM)


def _chunks() -> list[KnowledgeChunk]:
    rows = [
        ("a1", "alpha text", "a.cbl", "ws1"),
        ("a2", "alpha two", "a.cbl", "ws1"),
        ("b1", "beta text", "b.cbl", "ws1"),
        ("c1", "gamma text", "a.cbl", "ws2"),
    ]
    return [
        KnowledgeChunk(
            id=cid,
            document_id="doc",
            content=text,
            chunk_index=i,
            metadata={"filename": fn, "workspace_id": ws},
        )
        for i, (cid, text, fn, ws) in enumerate(rows)
    ]


@pytest.fixture(params=["memory", "chroma"])
def index(request: pytest.FixtureRequest, tmp_path: Path) -> VectorIndex:
    chunks = _chunks()
    if request.param == "memory":
        idx: VectorIndex = InMemoryIndex(expected_dimension=DIM)
    else:
        idx = ChromaIndex(tmp_path, "index_mgmt_test", expected_dimension=DIM)
    idx.add(EmbeddingService(PROVIDER).embed_chunks(chunks), chunks)
    return idx


def test_list_chunks_without_filter_returns_everything(index: VectorIndex) -> None:
    assert sorted(c.chunk_id for c in index.list_chunks()) == ["a1", "a2", "b1", "c1"]


def test_list_chunks_carries_text_and_metadata(index: VectorIndex) -> None:
    by_id = {c.chunk_id: c for c in index.list_chunks({"filename": "b.cbl"})}
    assert list(by_id) == ["b1"]
    assert by_id["b1"].content == "beta text"
    assert by_id["b1"].metadata["workspace_id"] == "ws1"


def test_list_chunks_with_one_and_two_key_filters(index: VectorIndex) -> None:
    one = {c.chunk_id for c in index.list_chunks({"filename": "a.cbl"})}
    two = {
        c.chunk_id
        for c in index.list_chunks({"filename": "a.cbl", "workspace_id": "ws1"})
    }
    assert one == {"a1", "a2", "c1"}
    assert two == {"a1", "a2"}


def test_list_chunks_order_is_deterministic(index: VectorIndex) -> None:
    assert [c.chunk_id for c in index.list_chunks()] == [
        c.chunk_id for c in index.list_chunks()
    ]


def test_delete_removes_only_matching_chunks_and_counts_them(
    index: VectorIndex,
) -> None:
    removed = index.delete({"filename": "a.cbl", "workspace_id": "ws1"})
    assert removed == 2
    assert sorted(c.chunk_id for c in index.list_chunks()) == ["b1", "c1"]
    assert not index.contains("a1")
    assert index.contains("c1")


def test_delete_with_no_match_removes_nothing(index: VectorIndex) -> None:
    assert index.delete({"filename": "missing.cbl"}) == 0
    assert index.size() == 4


def test_delete_requires_a_filter(index: VectorIndex) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        index.delete({})
    assert index.size() == 4


def test_default_implementations_raise_not_implemented() -> None:
    class Bare(VectorIndex):
        def add(self, embeddings, chunks=None): ...
        def contains(self, chunk_id):
            return False

        def get(self, chunk_id):
            return None

        def size(self):
            return 0

        def search(self, query_vector, top_k, filter_metadata=None):
            return []

    bare = Bare()
    with pytest.raises(NotImplementedError):
        bare.list_chunks()
    with pytest.raises(NotImplementedError):
        bare.delete({"a": "b"})
