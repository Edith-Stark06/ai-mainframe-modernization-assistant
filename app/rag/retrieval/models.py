from dataclasses import dataclass
from typing import Any, Mapping

from app.rag.models import _freeze_metadata, _to_json_compatible


@dataclass(frozen=True)
class RetrievalResult:
    """
    An immutable domain representation for a retrieved knowledge chunk.
    """

    chunk_id: str
    document_id: str
    content: str
    chunk_index: int
    metadata: Mapping[str, Any]
    score: float

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.chunk_id.strip():
            raise ValueError("chunk_id cannot be empty")
        if not self.document_id or not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.content or not self.content.strip():
            raise ValueError("content cannot be empty")
        if self.chunk_index < 0:
            raise ValueError("chunk_index cannot be negative")

        # Freeze metadata to ensure immutability
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the retrieval result to a JSON-compatible dictionary.
        """
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "metadata": _to_json_compatible(self.metadata),
            "score": self.score,
        }
