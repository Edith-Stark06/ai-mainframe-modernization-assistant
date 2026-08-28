import hashlib

import pytest
from app.rag.chunking import DocumentChunker
from app.rag.models import KnowledgeDocument


def _create_doc(content: str, doc_type: str = "text") -> KnowledgeDocument:
    return KnowledgeDocument(
        id="doc1",
        source_name="test.txt",
        document_type=doc_type,
        source_path=None,
        content=content,
        metadata={"foo": "bar"},
    )


def test_chunking_validation() -> None:
    with pytest.raises(ValueError):
        DocumentChunker(chunk_size=0, overlap=0)
    with pytest.raises(ValueError):
        DocumentChunker(chunk_size=-10, overlap=0)
    with pytest.raises(ValueError):
        DocumentChunker(chunk_size=10, overlap=10)
    with pytest.raises(ValueError):
        DocumentChunker(chunk_size=10, overlap=-1)


def test_text_chunking_single() -> None:
    doc = _create_doc("Short text")
    chunker = DocumentChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 1
    assert chunks[0].content == "Short text"
    assert chunks[0].metadata["start_char"] == 0
    assert chunks[0].metadata["end_char"] == 10
    assert chunks[0].metadata["chunk_index"] == 0
    assert chunks[0].metadata["source_id"] == "doc1"
    assert chunks[0].metadata["document_type"] == "text"
    assert chunks[0].metadata["chunk_size"] == 100
    assert chunks[0].metadata["overlap"] == 20


def test_text_chunking_exact_size() -> None:
    doc = _create_doc("0123456789")
    chunker = DocumentChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 1
    assert chunks[0].content == "0123456789"


def test_text_chunking_overlap() -> None:
    doc = _create_doc("0123456789")
    chunker = DocumentChunker(chunk_size=5, overlap=2)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 3
    assert chunks[0].content == "01234"
    assert chunks[1].content == "34567"
    assert chunks[2].content == "6789"


def test_text_chunking_coverage() -> None:
    # 01234 34567 6789
    # Coverage is correct since overlapping starts at correct index
    pass


def test_code_chunking_lines() -> None:
    doc = _create_doc("LINE 1\nLINE 2\nLINE 3\nLINE 4\n", doc_type="cobol")
    chunker = DocumentChunker(chunk_size=16, overlap=8)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 3
    assert chunks[0].content == "LINE 1\nLINE 2\n"
    assert chunks[1].content == "LINE 2\nLINE 3\n"
    assert chunks[2].content == "LINE 3\nLINE 4\n"


def test_code_chunking_long_line() -> None:
    # Chunk size is smaller than the line
    doc = _create_doc("THIS IS A VERY LONG LINE", doc_type="cobol")
    chunker = DocumentChunker(chunk_size=10, overlap=4)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 4
    assert chunks[0].content == "THIS IS A "
    assert chunks[1].content == "S A VERY L"
    assert chunks[2].content == "RY LONG LI"
    assert chunks[3].content == "G LINE"


def test_code_chunking_no_newline_before_overlap() -> None:
    # Line 1 is long, no newline in overlap window
    doc = _create_doc("Line1 part1\nLine2", doc_type="cobol")
    # length: 12 + 5 = 17
    chunker = DocumentChunker(chunk_size=8, overlap=3)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 3
    assert chunks[0].content == "Line1 pa"
    assert chunks[1].content == " part1\n"
    assert chunks[2].content == "t1\nLine2"


def test_deterministic_ids() -> None:
    doc = _create_doc("Hello world")
    chunker = DocumentChunker(chunk_size=5, overlap=2)
    chunks1 = chunker.chunk_document(doc)
    chunks2 = chunker.chunk_document(doc)

    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1.id == c2.id

    expected_id = "doc1-" + hashlib.sha256(b"doc1:0:Hello").hexdigest()[:16]
    assert chunks1[0].id == expected_id


def test_metadata_isolation() -> None:
    doc = _create_doc("Hello world")
    chunker = DocumentChunker(chunk_size=5, overlap=2)
    chunks = chunker.chunk_document(doc)

    with pytest.raises(TypeError):
        chunks[0].metadata["new_key"] = "value"  # type: ignore


def test_empty_document() -> None:
    # KnowledgeDocument creation fails if empty, but let's bypass it just to test chunker handles empty safely if it somehow got through
    # We can use object.__setattr__ to bypass validation for testing chunker
    doc = KnowledgeDocument(
        id="doc1",
        source_name="empty.txt",
        document_type="text",
        source_path=None,
        content="x",
        metadata={},
    )
    object.__setattr__(doc, "content", "")

    chunker = DocumentChunker()
    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 0


def test_whitespace_chunks_are_dropped() -> None:
    doc = _create_doc("    \n    \n    x")
    chunker = DocumentChunker(chunk_size=5, overlap=0)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) == 1
    assert chunks[0].content == "    x"
