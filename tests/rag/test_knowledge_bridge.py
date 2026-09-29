"""
Tests for :mod:`app.rag.knowledge_bridge`.

Purpose:
    Verify :func:`to_rag_chunks` correctly adapts real
    :class:`~app.knowledge.ingest.KnowledgeIngestor` output into the
    RAG layer's own chunk shape, including extra metadata merging and
    deterministic chunk_index assignment.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.knowledge.ingest import KnowledgeIngestor
from app.rag.knowledge_bridge import to_rag_chunks

_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ELIG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-AGE    PIC 9(3) VALUE 0.
       01 WS-RESULT PIC X(10) VALUE SPACE.
       PROCEDURE DIVISION.
       CHECK-AGE.
           IF WS-AGE >= 18
               MOVE 'ELIGIBLE' TO WS-RESULT
           ELSE
               MOVE 'DENIED' TO WS-RESULT
           END-IF.
           STOP RUN.
"""


def test_converts_every_chunk() -> None:
    result = KnowledgeIngestor().ingest_program("ELIG", _SOURCE)
    chunks = to_rag_chunks(result)
    assert len(chunks) == len(result.chunks)
    assert len(chunks) > 0


def test_chunk_index_is_positional() -> None:
    result = KnowledgeIngestor().ingest_program("ELIG", _SOURCE)
    chunks = to_rag_chunks(result)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_document_id_is_provenance_source_id() -> None:
    result = KnowledgeIngestor().ingest_program("ELIG", _SOURCE)
    chunks = to_rag_chunks(result)
    assert all(c.document_id == "ELIG" for c in chunks)


def test_id_matches_source_chunk_id() -> None:
    result = KnowledgeIngestor().ingest_program("ELIG", _SOURCE)
    chunks = to_rag_chunks(result)
    assert {c.id for c in chunks} == {c.chunk_id for c in result.chunks}


def test_extra_metadata_is_merged_and_overrides() -> None:
    result = KnowledgeIngestor().ingest_program("ELIG", _SOURCE)
    chunks = to_rag_chunks(
        result, extra_metadata={"workspace_id": "ws-1", "filename": "elig.cbl"}
    )
    for c in chunks:
        assert c.metadata["workspace_id"] == "ws-1"
        assert c.metadata["filename"] == "elig.cbl"


def test_metadata_values_are_chroma_safe_scalar_types() -> None:
    """Every metadata value must be str/int/float/bool -- anything else
    would make ChromaIndex.add raise (see its own _validate_metadata_value)."""
    result = KnowledgeIngestor().ingest_program("ELIG", _SOURCE)
    chunks = to_rag_chunks(result)
    for c in chunks:
        for value in c.metadata.values():
            assert isinstance(value, (str, int, float, bool))


def test_minimal_program_still_converts_without_error() -> None:
    """A minimal (but non-empty) program still produces at least the
    whole-source chunk -- to_rag_chunks never assumes a rich set of
    artifacts is present."""
    minimal_source = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MIN.\n"
        "       PROCEDURE DIVISION.\n"
        "       STOP RUN.\n"
    )
    result = KnowledgeIngestor().ingest_program("MIN", minimal_source)
    chunks = to_rag_chunks(result)
    assert len(chunks) > 0
    assert all(c.content.strip() for c in chunks)
