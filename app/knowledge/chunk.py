"""
The canonical Phase 8 knowledge chunk (#122 Step 1).

A :class:`KnowledgeChunk` is an immutable, deterministically-identified
unit of modernization knowledge that **cannot exist without provenance**.
It is a Phase 8 model (richer, provenance-enforcing) that complements the
generic :class:`app.rag.models.KnowledgeChunk`; retrieval keeps the full
:class:`~app.knowledge.provenance.Provenance` on every result.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.knowledge.errors import ProvenanceError
from app.knowledge.provenance import Provenance
from app.knowledge.version import KNOWLEDGE_SCHEMA_VERSION

__all__ = ["ChunkType", "KnowledgeChunk"]


class ChunkType(str, Enum):
    COBOL_DIVISION = "cobol_division"
    COBOL_PARAGRAPH = "cobol_paragraph"
    COBOL_SOURCE = "cobol_source"
    COPYBOOK = "copybook"
    JCL_STEP = "jcl_step"
    METADATA_RECORD = "metadata_record"
    AST_NODE = "ast_node"
    IR_MODULE = "ir_module"
    CFG_REGION = "cfg_region"
    DEPENDENCY = "dependency"
    BUSINESS_RULE = "business_rule"
    RISK = "risk"
    MODERNIZATION_PATTERN = "modernization_pattern"
    MODERNIZATION_STRATEGY = "modernization_strategy"
    JAVA_CLASS = "java_class"
    JAVA_METHOD = "java_method"


def compute_chunk_id(
    *,
    source_id: str,
    artifact_version: str,
    chunk_type: ChunkType,
    location_key: str,
    content: str,
) -> str:
    """Deterministic, collision-resistant chunk id (no random UUIDs)."""
    h = hashlib.sha256()
    h.update(
        "\x1f".join(
            (
                source_id,
                artifact_version,
                chunk_type.value,
                location_key,
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        ).encode("utf-8")
    )
    return f"{chunk_type.value}-{h.hexdigest()[:16]}"


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(..., min_length=1)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION
    chunk_type: ChunkType
    content: str = Field(..., min_length=1)
    content_hash: str
    provenance: Provenance
    #: extra queryable, JSON-safe attributes (never a substitute for provenance)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "KnowledgeChunk":
        self.provenance.validate_complete()
        if not self.content.strip():
            raise ProvenanceError(f"chunk {self.chunk_id} has blank content")
        want = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_hash != want:
            raise ProvenanceError(
                f"chunk {self.chunk_id} content_hash does not match content"
            )
        return self

    @classmethod
    def create(
        cls,
        *,
        chunk_type: ChunkType,
        content: str,
        provenance: Provenance,
        location_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> "KnowledgeChunk":
        provenance.validate_complete()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_id = compute_chunk_id(
            source_id=provenance.source_id,
            artifact_version=provenance.artifact_version,
            chunk_type=chunk_type,
            location_key=location_key,
            content=content,
        )
        return cls(
            chunk_id=chunk_id,
            chunk_type=chunk_type,
            content=content,
            content_hash=content_hash,
            provenance=provenance,
            metadata=metadata or {},
        )

    def index_metadata(self) -> dict[str, Any]:
        """Flat metadata stored in the vector index (queryable filters)."""
        md: dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type.value,
            "schema_version": self.schema_version,
            "content_hash": self.content_hash,
        }
        md.update(self.provenance.to_metadata())
        for k, v in self.metadata.items():
            if isinstance(v, (str, int, float, bool)) and k not in md:
                md[k] = v
        return md

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "schema_version": self.schema_version,
            "chunk_type": self.chunk_type.value,
            "content": self.content,
            "content_hash": self.content_hash,
            "provenance": self.provenance.model_dump(mode="json"),
            "metadata": self.metadata,
        }
