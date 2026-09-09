"""
Retrieval with a hard project/workspace scope (#122 Step 7, security).

:class:`KnowledgeRetriever` wraps a :class:`~app.knowledge.index.KnowledgeIndex`
and, when constructed with ``allowed_source_ids``, injects a filter so a
query can never pull a chunk from a program outside the current
project/workspace — cross-project retrieval is impossible, not merely
discouraged.
"""

from __future__ import annotations

from typing import Any

from app.knowledge.index import KnowledgeIndex, RetrievedChunk
from app.knowledge.errors import IndexError_

__all__ = ["KnowledgeRetriever"]


class KnowledgeRetriever:
    def __init__(
        self,
        index: KnowledgeIndex,
        *,
        allowed_source_ids: set[str] | None = None,
    ) -> None:
        self._index = index
        self._scope = set(allowed_source_ids) if allowed_source_ids else None

    @property
    def scope(self) -> set[str] | None:
        return set(self._scope) if self._scope is not None else None

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        merged: dict[str, Any] = dict(filters or {})
        if self._scope is not None:
            requested = merged.get("source_id")
            if requested is None:
                merged["source_id"] = sorted(self._scope)
            else:
                asked = {requested} if isinstance(requested, str) else set(requested)
                outside = asked - self._scope
                if outside:
                    raise IndexError_(
                        f"source_id filter {sorted(outside)} is outside the "
                        f"retriever's project scope"
                    )
                merged["source_id"] = sorted(asked)
        hits = self._index.search(query, top_k=top_k, filters=merged)
        # defensive: never return a chunk outside scope even if a store bug slips
        if self._scope is not None:
            hits = [h for h in hits if h.provenance.source_id in self._scope]
        return hits

    def retrieve_for_source(
        self, query: str, source_id: str, *, top_k: int = 5, **kw: Any
    ) -> list[RetrievedChunk]:
        filters = dict(kw.pop("filters", {}) or {})
        filters["source_id"] = source_id
        return self.retrieve(query, top_k=top_k, filters=filters)
