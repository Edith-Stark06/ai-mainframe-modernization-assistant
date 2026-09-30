"""index_program: one pipeline for chat and evaluation; stale chunks replaced."""

from __future__ import annotations

from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.indexing.memory import InMemoryIndex
from app.rag.ingestion import index_program

PROVIDER = DeterministicFakeProvider(dimension=32)

_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PIPE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-LIMIT PIC 9(5) VALUE {limit}.
       01  WS-STATUS PIC X(8).
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-LIMIT > {limit}
               MOVE 'OVER' TO WS-STATUS
           END-IF.
           STOP RUN.
"""


def _index(index: InMemoryIndex, limit: int, replace: bool = True):
    identity = {"workspace_id": "ws", "filename": "pipe.cbl"}
    return index_program(
        source_id="PIPE",
        source_text=_SOURCE.format(limit=limit),
        source_path="pipe.cbl",
        extra_metadata=identity,
        embedding_provider=PROVIDER,
        index=index,
        replace_filter=identity if replace else None,
    )


def test_first_index_reports_chunks_and_types() -> None:
    index = InMemoryIndex(expected_dimension=32)
    summary = _index(index, 100)
    assert summary.chunks_indexed == index.size() > 0
    assert summary.chunks_replaced == 0
    assert sum(summary.chunk_types.values()) == summary.chunks_indexed
    assert "data_item" in summary.chunk_types


def test_reindexing_an_edited_file_replaces_instead_of_accumulating() -> None:
    index = InMemoryIndex(expected_dimension=32)
    _index(index, 100)
    size_after_first = index.size()

    summary = _index(index, 999)  # edited: different content hashes
    assert summary.chunks_replaced == size_after_first
    assert index.size() == summary.chunks_indexed
    texts = " ".join(c.content for c in index.list_chunks())
    assert "999" in texts
    assert "VALUE 100" not in texts  # nothing stale survives


def test_without_a_replace_filter_stale_chunks_remain() -> None:
    index = InMemoryIndex(expected_dimension=32)
    _index(index, 100, replace=False)
    first = index.size()
    _index(index, 999, replace=False)
    assert index.size() > first


def test_other_files_are_untouched_by_a_reindex() -> None:
    index = InMemoryIndex(expected_dimension=32)
    index_program(
        source_id="OTHER",
        source_text=_SOURCE.format(limit=5),
        source_path="other.cbl",
        extra_metadata={"workspace_id": "ws", "filename": "other.cbl"},
        embedding_provider=PROVIDER,
        index=index,
    )
    other_ids = {c.chunk_id for c in index.list_chunks({"filename": "other.cbl"})}
    _index(index, 100)
    _index(index, 200)
    assert {
        c.chunk_id for c in index.list_chunks({"filename": "other.cbl"})
    } == other_ids


def test_an_index_that_cannot_delete_still_indexes() -> None:
    class NoDelete(InMemoryIndex):
        def delete(self, filter_metadata):  # type: ignore[override]
            raise NotImplementedError

    index = NoDelete(expected_dimension=32)
    _index(index, 100)
    summary = _index(index, 200)
    assert summary.chunks_replaced == 0
    assert summary.chunks_indexed > 0
