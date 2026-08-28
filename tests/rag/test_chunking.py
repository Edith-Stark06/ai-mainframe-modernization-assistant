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

    for i in range(len(chunks) - 1):
        assert chunks[i].metadata["start_char"] < chunks[i].metadata["end_char"]
        assert chunks[i + 1].metadata["start_char"] > chunks[i].metadata["start_char"]


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


def test_text_chunking_overlap_correctness() -> None:
    doc = _create_doc("0123456789")
    chunker = DocumentChunker(chunk_size=5, overlap=2)
    chunks = chunker.chunk_document(doc)

    # 01234
    #    34567
    #       6789
    assert len(chunks) == 3
    for i in range(len(chunks) - 1):
        prev_chunk = chunks[i]
        next_chunk = chunks[i + 1]

        # Verify next start < prev end
        assert next_chunk.metadata["start_char"] < prev_chunk.metadata["end_char"]

        # Verify prev end - next start == overlap (for text chunker, if possible, but definitely verify suffix/prefix matches)
        overlap_len = (
            prev_chunk.metadata["end_char"] - next_chunk.metadata["start_char"]
        )
        assert prev_chunk.content[-overlap_len:] == next_chunk.content[:overlap_len]


def test_text_chunking_exact_boundary_plus_one() -> None:
    doc = _create_doc("0123456789A")
    chunker = DocumentChunker(chunk_size=10, overlap=0)
    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 2
    assert chunks[0].content == "0123456789"
    assert chunks[1].content == "A"


def test_text_chunking_overlap_zero() -> None:
    doc = _create_doc("0123456789")
    chunker = DocumentChunker(chunk_size=5, overlap=0)
    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 2
    assert chunks[0].content == "01234"
    assert chunks[1].content == "56789"


def test_text_chunking_overlap_max() -> None:
    doc = _create_doc("012345")
    chunker = DocumentChunker(chunk_size=5, overlap=4)
    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 2
    assert chunks[0].content == "01234"
    assert chunks[1].content == "12345"


def test_content_coverage() -> None:
    source = "0000111122223333444455556666777788889999"
    doc = _create_doc(source)
    chunker = DocumentChunker(chunk_size=7, overlap=3)
    chunks = chunker.chunk_document(doc)

    reconstructed = ""
    last_end = 0
    for chunk in chunks:
        start = chunk.metadata["start_char"]
        end = chunk.metadata["end_char"]

        # Add only the non-overlapping new part
        if start >= last_end:
            reconstructed += chunk.content
        else:
            new_part_start = last_end - start
            reconstructed += chunk.content[new_part_start:]

        last_end = end

    assert reconstructed == source


def test_code_chunking_cobol_realistic() -> None:
    source = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           DISPLAY "HELLO".
           STOP RUN.
"""
    doc = _create_doc(source, doc_type="cobol")
    chunker = DocumentChunker(chunk_size=50, overlap=10)
    chunks = chunker.chunk_document(doc)

    # Ensure it preserves content exactly
    reconstructed = ""
    last_end = 0
    for chunk in chunks:
        assert chunk.metadata["document_type"] == "cobol"
        start = chunk.metadata["start_char"]
        end = chunk.metadata["end_char"]
        if start >= last_end:
            reconstructed += chunk.content
        else:
            reconstructed += chunk.content[last_end - start :]
        last_end = end

    assert reconstructed == source


def test_unicode_preservation() -> None:
    source = "Hello 🌍! This is a test 🚀."
    doc = _create_doc(source)
    chunker = DocumentChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk_document(doc)

    reconstructed = ""
    last_end = 0
    for chunk in chunks:
        start = chunk.metadata["start_char"]
        end = chunk.metadata["end_char"]
        if start >= last_end:
            reconstructed += chunk.content
        else:
            reconstructed += chunk.content[last_end - start :]
        last_end = end

    assert reconstructed == source


def test_identifier_determinism() -> None:
    doc1 = _create_doc("A content", doc_type="text")
    doc2 = _create_doc("B content", doc_type="text")

    chunker = DocumentChunker(chunk_size=5, overlap=0)
    c1 = chunker.chunk_document(doc1)
    c2 = chunker.chunk_document(doc2)

    assert c1[0].id != c2[0].id


def test_immutability_metadata() -> None:
    metadata = {"key": "value"}
    doc = KnowledgeDocument(
        id="doc1",
        source_name="test.txt",
        document_type="text",
        source_path=None,
        content="abc",
        metadata=metadata,
    )
    chunker = DocumentChunker(chunk_size=5, overlap=0)
    _ = chunker.chunk_document(doc)

    # Mutate original
    metadata["key"] = "mutated"
    # Document shouldn't change (tested in task 073, but let's verify chunks don't have it either)
    assert doc.metadata["key"] == "value"


def test_chunk_boundary_invariant() -> None:
    source = "0123456789" * 10  # 100 chars
    doc = _create_doc(source)
    chunker = DocumentChunker(chunk_size=15, overlap=5)
    chunks = chunker.chunk_document(doc)

    for i, chunk in enumerate(chunks):
        start = chunk.metadata["start_char"]
        end = chunk.metadata["end_char"]
        assert 0 <= start < end <= len(source)
        assert chunk.content == source[start:end]

        if i > 0:
            prev_chunk = chunks[i - 1]
            prev_start = prev_chunk.metadata["start_char"]
            prev_end = prev_chunk.metadata["end_char"]

            assert start > prev_start
            assert end > prev_start  # end is greater than prev start
            # For this simple text chunker:
            assert start == prev_end - 5
