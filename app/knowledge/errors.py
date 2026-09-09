"""Exceptions for the Phase 8 knowledge / grounding layer (#122)."""

from __future__ import annotations


class KnowledgeError(Exception):
    """Base class for every knowledge-layer error."""


class ProvenanceError(KnowledgeError):
    """A chunk or context item is missing required source identity / provenance.

    The Phase 8 non-negotiable rule: nothing without provenance is
    indexed or sent to a model.
    """


class ChunkingError(KnowledgeError):
    """A source / analysis artifact could not be chunked deterministically."""


class EmbeddingIdentityError(KnowledgeError):
    """Vectors from different embedding models would be mixed in one index."""


class IndexError_(KnowledgeError):
    """Index insert / search precondition failed."""


__all__ = [
    "KnowledgeError",
    "ProvenanceError",
    "ChunkingError",
    "EmbeddingIdentityError",
    "IndexError_",
]
