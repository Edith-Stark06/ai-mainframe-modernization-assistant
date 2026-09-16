import copy
import json
from dataclasses import FrozenInstanceError

import pytest

from app.rag.models import (
    ImmutableDict,
    KnowledgeChunk,
    KnowledgeDocument,
    _freeze_metadata,
)


def test_immutable_dict_prevents_mutation() -> None:
    d = ImmutableDict({"a": 1})

    with pytest.raises(TypeError):
        d["b"] = 2

    with pytest.raises(TypeError):
        del d["a"]

    with pytest.raises(TypeError):
        d.clear()

    with pytest.raises(TypeError):
        d.pop("a")

    with pytest.raises(TypeError):
        d.popitem()

    with pytest.raises(TypeError):
        d.update({"c": 3})

    with pytest.raises(TypeError):
        d.setdefault("d", 4)


def test_immutable_dict_supports_deepcopy() -> None:
    """
    Regression test: copy.deepcopy() previously crashed on ImmutableDict
    (and any structure containing one, e.g. RAGRequest.modernization_context)
    with `TypeError: Immutable mapping`, because the default deepcopy
    reconstruction path calls __setitem__ on a fresh instance. Since
    ImmutableDict contents are always fully, recursively frozen at
    construction, __deepcopy__ should simply return the same instance.
    """
    original = _freeze_metadata({"a": {"b": [1, 2, 3]}, "c": "d"})
    copied = copy.deepcopy(original)

    assert copied is original

    nested = {"outer": original}
    deep_copied_container = copy.deepcopy(nested)
    assert deep_copied_container["outer"] is original


def test_freeze_metadata_isolation() -> None:
    original = {
        "str": "value",
        "nested_dict": {"list": [1, 2, 3]},
    }
    frozen = _freeze_metadata(original)

    assert isinstance(frozen, ImmutableDict)
    assert isinstance(frozen["nested_dict"], ImmutableDict)
    assert isinstance(frozen["nested_dict"]["list"], tuple)

    # Modifying the original doesn't affect the frozen metadata
    original["nested_dict"]["list"].append(4)  # type: ignore
    original["str"] = "changed"

    assert frozen["str"] == "value"
    assert frozen["nested_dict"]["list"] == (1, 2, 3)


def test_knowledge_document_construction() -> None:
    doc = KnowledgeDocument(
        id="doc-123",
        source_name="program.cbl",
        document_type="COBOL",
        source_path="/path/to/program.cbl",
        content="IDENTIFICATION DIVISION.",
        metadata={"author": "user1"},
    )
    assert doc.id == "doc-123"
    assert doc.source_name == "program.cbl"
    assert doc.document_type == "COBOL"
    assert doc.source_path == "/path/to/program.cbl"
    assert doc.content == "IDENTIFICATION DIVISION."
    assert isinstance(doc.metadata, ImmutableDict)
    assert doc.metadata["author"] == "user1"


def test_knowledge_document_validation() -> None:
    with pytest.raises(ValueError, match="Document ID cannot be empty."):
        KnowledgeDocument(
            id="",
            source_name="program.cbl",
            document_type="COBOL",
            source_path=None,
            content="content",
            metadata={},
        )

    with pytest.raises(ValueError, match="Document content cannot be empty."):
        KnowledgeDocument(
            id="doc-1",
            source_name="program.cbl",
            document_type="COBOL",
            source_path=None,
            content="",
            metadata={},
        )


def test_knowledge_document_immutability() -> None:
    doc = KnowledgeDocument(
        id="doc-123",
        source_name="program.cbl",
        document_type="COBOL",
        source_path=None,
        content="CONTENT",
        metadata={"key": "value"},
    )

    with pytest.raises(FrozenInstanceError):
        doc.id = "doc-456"  # type: ignore

    with pytest.raises(TypeError):
        doc.metadata["key"] = "new_value"  # type: ignore


def test_knowledge_document_to_dict_and_json_serialization() -> None:
    doc = KnowledgeDocument(
        id="doc-123",
        source_name="program.cbl",
        document_type="COBOL",
        source_path="/path/to/program.cbl",
        content="CONTENT",
        metadata={"nested": [1, 2, 3]},
    )
    d = doc.to_dict()
    assert d == {
        "id": "doc-123",
        "source_name": "program.cbl",
        "document_type": "COBOL",
        "source_path": "/path/to/program.cbl",
        "content": "CONTENT",
        "metadata": {"nested": [1, 2, 3]},
    }
    # Ensure it's json serializable without str() or repr() fallbacks
    json_str = json.dumps(d)
    assert '"doc-123"' in json_str
    assert "[1, 2, 3]" in json_str


def test_knowledge_chunk_construction() -> None:
    chunk = KnowledgeChunk(
        id="chunk-001",
        document_id="doc-123",
        content="chunk content",
        chunk_index=0,
        metadata={"loc": "line 1"},
    )
    assert chunk.id == "chunk-001"
    assert chunk.document_id == "doc-123"
    assert chunk.content == "chunk content"
    assert chunk.chunk_index == 0
    assert isinstance(chunk.metadata, ImmutableDict)
    assert chunk.metadata["loc"] == "line 1"


def test_knowledge_chunk_validation() -> None:
    with pytest.raises(ValueError, match="Chunk ID cannot be empty."):
        KnowledgeChunk(
            id="",
            document_id="doc-1",
            content="content",
            chunk_index=0,
            metadata={},
        )

    with pytest.raises(ValueError, match="Parent document ID cannot be empty."):
        KnowledgeChunk(
            id="chunk-1",
            document_id="",
            content="content",
            chunk_index=0,
            metadata={},
        )

    with pytest.raises(ValueError, match="Chunk content cannot be empty."):
        KnowledgeChunk(
            id="chunk-1",
            document_id="doc-1",
            content="",
            chunk_index=0,
            metadata={},
        )

    with pytest.raises(ValueError, match="Chunk index cannot be negative."):
        KnowledgeChunk(
            id="chunk-1",
            document_id="doc-1",
            content="content",
            chunk_index=-1,
            metadata={},
        )


def test_knowledge_chunk_immutability() -> None:
    chunk = KnowledgeChunk(
        id="chunk-001",
        document_id="doc-123",
        content="content",
        chunk_index=0,
        metadata={"key": "value"},
    )

    with pytest.raises(FrozenInstanceError):
        chunk.content = "new content"  # type: ignore

    with pytest.raises(TypeError):
        chunk.metadata["key"] = "new_value"  # type: ignore


def test_knowledge_chunk_to_dict_and_json_serialization() -> None:
    chunk = KnowledgeChunk(
        id="chunk-001",
        document_id="doc-123",
        content="content",
        chunk_index=0,
        metadata={"tags": ["important"]},
    )
    d = chunk.to_dict()
    assert d == {
        "id": "chunk-001",
        "document_id": "doc-123",
        "content": "content",
        "chunk_index": 0,
        "metadata": {"tags": ["important"]},
    }
    json_str = json.dumps(d)
    assert '"chunk-001"' in json_str
    assert '["important"]' in json_str


def test_metadata_ordering_determinism() -> None:
    """Verify that metadata keys are sorted deterministically."""
    # Create two chunks with identical metadata but different insertion order
    meta1 = {"b": 2, "c": 3, "a": 1}
    meta2 = {"a": 1, "c": 3, "b": 2}

    chunk1 = KnowledgeChunk(
        id="chunk", document_id="doc", content="x", chunk_index=0, metadata=meta1
    )
    chunk2 = KnowledgeChunk(
        id="chunk", document_id="doc", content="x", chunk_index=0, metadata=meta2
    )

    dict1 = chunk1.to_dict()
    dict2 = chunk2.to_dict()

    # The json serialization string should be strictly identical,
    # ensuring no non-deterministic hash ordering.
    assert json.dumps(dict1, sort_keys=True) == json.dumps(dict2, sort_keys=True)

    # In Python 3.7+, dicts preserve insertion order. Our `_freeze_metadata`
    # sorts the keys, so `list(chunk1.metadata.keys())` should equal `['a', 'b', 'c']`
    assert list(chunk1.metadata.keys()) == ["a", "b", "c"]
    assert list(chunk2.metadata.keys()) == ["a", "b", "c"]


def test_unsupported_metadata_rejection() -> None:
    class CustomObj:
        pass

    with pytest.raises(ValueError, match="Unsupported metadata type"):
        KnowledgeDocument(
            id="doc",
            source_name="src",
            document_type="type",
            source_path=None,
            content="content",
            metadata={"key": CustomObj()},
        )


def test_metadata_keys_must_be_strings() -> None:
    with pytest.raises(ValueError, match="Metadata keys must be strings"):
        KnowledgeChunk(
            id="chunk",
            document_id="doc",
            content="content",
            chunk_index=0,
            metadata={1: "value"},  # type: ignore
        )


def test_whitespace_validation() -> None:
    with pytest.raises(ValueError, match="Document ID cannot be empty"):
        KnowledgeDocument(
            id="   ",
            source_name="src",
            document_type="type",
            source_path=None,
            content="content",
            metadata={},
        )

    with pytest.raises(ValueError, match="Document content cannot be empty"):
        KnowledgeDocument(
            id="doc",
            source_name="src",
            document_type="type",
            source_path=None,
            content="   ",
            metadata={},
        )

    with pytest.raises(ValueError, match="Chunk ID cannot be empty"):
        KnowledgeChunk(
            id="   ", document_id="doc", content="content", chunk_index=0, metadata={}
        )

    with pytest.raises(ValueError, match="Parent document ID cannot be empty"):
        KnowledgeChunk(
            id="chunk", document_id="   ", content="content", chunk_index=0, metadata={}
        )

    with pytest.raises(ValueError, match="Chunk content cannot be empty"):
        KnowledgeChunk(
            id="chunk", document_id="doc", content="   ", chunk_index=0, metadata={}
        )


def test_structural_equality() -> None:
    doc1 = KnowledgeDocument(
        id="doc",
        source_name="src",
        document_type="type",
        source_path=None,
        content="content",
        metadata={"a": 1},
    )
    doc2 = KnowledgeDocument(
        id="doc",
        source_name="src",
        document_type="type",
        source_path=None,
        content="content",
        metadata={"a": 1},
    )
    doc3 = KnowledgeDocument(
        id="doc2",
        source_name="src",
        document_type="type",
        source_path=None,
        content="content",
        metadata={"a": 1},
    )

    assert doc1 == doc2
    assert doc1 != doc3


def test_metadata_isolation() -> None:
    mutable_dict = {"nested": {"value": 1}}
    chunk = KnowledgeChunk(
        id="c1",
        document_id="d1",
        content="content",
        chunk_index=0,
        metadata=mutable_dict,
    )

    # Mutating original dict shouldn't affect stored
    mutable_dict["nested"]["value"] = 2

    assert chunk.metadata["nested"]["value"] == 1

    # Attempting to mutate through the object should fail
    with pytest.raises(TypeError):
        chunk.metadata["nested"]["value"] = 3  # type: ignore
