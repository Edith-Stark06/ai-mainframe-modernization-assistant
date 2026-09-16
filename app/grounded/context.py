"""
The grounded context object (#123) — everything the model is allowed to
see, and nothing without provenance.

``GroundedContext`` holds three lanes:

* ``source_context``   — verbatim COBOL slices (DETERMINISTIC_FACT)
* ``analysis_context`` — deterministic Phase 1–5 objects (DETERMINISTIC_FACT)
* ``retrieved_context`` — RAG hits from #122 (RETRIEVED_KNOWLEDGE)

:meth:`GroundedContext.validate` is the hard boundary: it raises
:class:`ContextProvenanceError` if *any* item lacks a usable
:class:`~app.knowledge.provenance.Provenance`. Call it before building a
prompt — :func:`app.grounded.prompt.build_grounded_prompt` does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.grounded.errors import ContextProvenanceError
from app.knowledge.provenance import Provenance

__all__ = ["Basis", "ContextItem", "GroundedContext"]


class Basis(str, Enum):
    DETERMINISTIC_FACT = "DETERMINISTIC_FACT"
    RETRIEVED_KNOWLEDGE = "RETRIEVED_KNOWLEDGE"
    AI_RECOMMENDATION = "AI_RECOMMENDATION"  # only produced by the model, never input


@dataclass(frozen=True)
class ContextItem:
    ref: str  # stable label used in the prompt, e.g. "E1"
    basis: Basis
    content: str
    provenance: Provenance
    kind: str  # "source" | "analysis" | "retrieved"
    score: float | None = None

    def citation(self) -> str:
        return self.provenance.citation()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "basis": self.basis.value,
            "kind": self.kind,
            "citation": self.citation(),
            "content": self.content,
            "provenance": self.provenance.model_dump(mode="json"),
            "score": self.score,
        }


@dataclass
class GroundedContext:
    question: str
    source_context: list[ContextItem] = field(default_factory=list)
    analysis_context: list[ContextItem] = field(default_factory=list)
    retrieved_context: list[ContextItem] = field(default_factory=list)

    def all_items(self) -> list[ContextItem]:
        return [*self.source_context, *self.analysis_context, *self.retrieved_context]

    @property
    def is_empty(self) -> bool:
        return not self.all_items()

    def by_ref(self) -> dict[str, ContextItem]:
        return {it.ref: it for it in self.all_items()}

    def validate(self) -> "GroundedContext":
        """Hard provenance boundary. Raises before anything reaches a model."""
        seen_refs: set[str] = set()
        for it in self.all_items():
            if not it.ref or it.ref in seen_refs:
                raise ContextProvenanceError(f"duplicate/empty context ref {it.ref!r}")
            seen_refs.add(it.ref)
            if it.provenance is None:  # type: ignore[unreachable]
                raise ContextProvenanceError(
                    f"context item {it.ref} has no provenance — refusing to send"
                )
            try:
                it.provenance.validate_complete()
            except Exception as exc:
                raise ContextProvenanceError(
                    f"context item {it.ref} provenance is unusable: {exc}"
                ) from exc
            if not it.content.strip():
                raise ContextProvenanceError(f"context item {it.ref} is empty")
        return self

    def provenance_manifest(self) -> list[dict[str, Any]]:
        return [
            {"ref": it.ref, "basis": it.basis.value, "citation": it.citation()}
            for it in self.all_items()
        ]
