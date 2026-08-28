"""
Knowledge-Base Models.

Purpose:
    Define a stable, provider-independent, and immutable representation
    of knowledge-base documents and chunks.
"""

from dataclasses import dataclass
from typing import Any, Mapping


class ImmutableDict(dict):
    """
    An immutable dictionary that can be natively serialized by JSON.
    """

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("Immutable mapping")

    def __delitem__(self, key: Any) -> None:
        raise TypeError("Immutable mapping")

    def clear(self) -> None:
        raise TypeError("Immutable mapping")

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("Immutable mapping")

    def popitem(self) -> Any:
        raise TypeError("Immutable mapping")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("Immutable mapping")

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("Immutable mapping")


def _freeze_metadata(data: Any) -> Any:
    """
    Recursively convert dictionaries to ImmutableDict and lists to tuples
    to prevent caller mutation and ensure immutability of the metadata.
    """
    if isinstance(data, Mapping):
        # Sort keys to ensure deterministic ordering of dictionaries
        return ImmutableDict(
            {k: _freeze_metadata(data[k]) for k in sorted(data.keys())}
        )
    elif isinstance(data, (list, tuple)):
        return tuple(_freeze_metadata(item) for item in data)
    return data


def _to_json_compatible(val: Any) -> Any:
    """
    Recursively convert ImmutableDict/tuple back to normal dict/list
    for strict JSON serialization.
    """
    if isinstance(val, Mapping):
        return {k: _to_json_compatible(v) for k, v in val.items()}
    elif isinstance(val, (tuple, list)):
        return [_to_json_compatible(v) for v in val]
    return val


@dataclass(frozen=True)
class KnowledgeDocument:
    """
    An immutable domain representation for a knowledge-base document.
    """

    id: str
    source_name: str
    document_type: str
    source_path: str | None
    content: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Document ID cannot be empty.")
        if not self.content:
            raise ValueError("Document content cannot be empty.")

        # Bypass frozen dataclass to set the frozen metadata safely
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the document to a deterministic JSON-compatible dictionary.
        """
        return {
            "id": self.id,
            "source_name": self.source_name,
            "document_type": self.document_type,
            "source_path": self.source_path,
            "content": self.content,
            "metadata": _to_json_compatible(self.metadata),
        }


@dataclass(frozen=True)
class KnowledgeChunk:
    """
    An immutable representation for a chunk extracted from a knowledge document.
    """

    id: str
    document_id: str
    content: str
    chunk_index: int
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Chunk ID cannot be empty.")
        if not self.document_id:
            raise ValueError("Parent document ID cannot be empty.")
        if not self.content:
            raise ValueError("Chunk content cannot be empty.")
        if self.chunk_index < 0:
            raise ValueError("Chunk index cannot be negative.")

        # Bypass frozen dataclass to set the frozen metadata safely
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the chunk to a deterministic JSON-compatible dictionary.
        """
        return {
            "id": self.id,
            "document_id": self.document_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "metadata": _to_json_compatible(self.metadata),
        }
