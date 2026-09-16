"""
Phase 8 knowledge-layer versioning (#122).

Every chunk and every index records the versions that produced it, so a
retrieval result is always attributable to a concrete pipeline state.

* ``KNOWLEDGE_SCHEMA_VERSION`` — the :class:`~app.knowledge.chunk.KnowledgeChunk`
  / :class:`~app.knowledge.provenance.Provenance` shape.
* ``CHUNKING_VERSION`` — the deterministic chunking logic in
  :mod:`app.knowledge.chunkers`; bump whenever chunk boundaries or ids
  could change for the same input.
* ``ANALYSIS_CONTRACT_VERSION`` — the deterministic Phase 1–5 analysis
  contract the ``analysis_context`` chunks were produced against (kept in
  step with :data:`app.dataset.version.ANALYSIS_VERSION`).
"""

from __future__ import annotations

from app.dataset.version import ANALYSIS_VERSION

KNOWLEDGE_SCHEMA_VERSION: str = "p8-knowledge-v1"
CHUNKING_VERSION: str = "p8-chunking-v1"
ANALYSIS_CONTRACT_VERSION: str = ANALYSIS_VERSION

__all__ = [
    "KNOWLEDGE_SCHEMA_VERSION",
    "CHUNKING_VERSION",
    "ANALYSIS_CONTRACT_VERSION",
]
