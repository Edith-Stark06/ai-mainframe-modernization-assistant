"""
Build a :class:`GroundedContext` from deterministic analysis + retrieval
(#123).

Deterministic facts (source slices, business rules, risks, dependencies,
strategy) come straight from the existing Phase 1–5
:class:`~app.dataset.analysis_bundle.AnalysisBundle`. Retrieved knowledge
comes from the #122 :class:`~app.knowledge.retrieval.KnowledgeRetriever`.
Every item is turned into a :class:`ContextItem` with its provenance.
"""

from __future__ import annotations

import re

from app.dataset.analysis_bundle import AnalysisBundle
from app.grounded.context import Basis, ContextItem, GroundedContext
from app.knowledge.chunkers import (
    chunk_business_rules,
    chunk_cobol_source,
    chunk_dependencies,
    chunk_risks,
    chunk_strategy,
)
from app.knowledge.retrieval import KnowledgeRetriever
from app.knowledge.version import ANALYSIS_CONTRACT_VERSION

__all__ = ["build_context_from_bundle"]

_MAX_SOURCE = 10
_MAX_ANALYSIS = 24
_WORD = re.compile(r"[A-Za-z0-9-]+")


def _tokens(text: str) -> set[str]:
    return {w.upper() for w in _WORD.findall(text)}


def build_context_from_bundle(
    question: str,
    bundle: AnalysisBundle,
    *,
    retriever: KnowledgeRetriever | None = None,
    retrieved_k: int = 4,
    analysis_version: str = ANALYSIS_CONTRACT_VERSION,
) -> GroundedContext:
    ctx = GroundedContext(question=question)
    q_tokens = _tokens(question)
    counter = 0

    def _ref() -> str:
        nonlocal counter
        counter += 1
        return f"E{counter}"

    sid = bundle.source_id

    # --- source lane (verbatim COBOL, deterministic fact) --------------
    source_chunks = chunk_cobol_source(
        sid, bundle.source, paragraph_names=list(bundle.paragraphs)
    )
    para_chunks = [c for c in source_chunks if c.provenance.paragraph]
    if len(para_chunks) <= _MAX_SOURCE:
        chosen = para_chunks
    else:
        scored = sorted(
            para_chunks,
            key=lambda c: (
                -len(_tokens(c.content) & q_tokens),
                c.provenance.line_start or 0,
            ),
        )
        chosen = scored[:_MAX_SOURCE]
        chosen.sort(key=lambda c: c.provenance.line_start or 0)
    for c in chosen:
        ctx.source_context.append(
            ContextItem(
                ref=_ref(),
                basis=Basis.DETERMINISTIC_FACT,
                content=c.content,
                provenance=c.provenance,
                kind="source",
            )
        )

    # --- analysis lane (deterministic objects) ------------------------
    analysis_chunks = (
        chunk_business_rules(
            bundle.business_rules,
            program_source_id=sid,
            analysis_version=analysis_version,
        )
        + chunk_risks(
            bundle.risks, program_source_id=sid, analysis_version=analysis_version
        )
        + chunk_strategy(
            bundle.strategy, program_source_id=sid, analysis_version=analysis_version
        )
        + chunk_dependencies(
            bundle.dependencies,
            program_source_id=sid,
            analysis_version=analysis_version,
        )
    )
    for c in analysis_chunks[:_MAX_ANALYSIS]:
        ctx.analysis_context.append(
            ContextItem(
                ref=_ref(),
                basis=Basis.DETERMINISTIC_FACT,
                content=c.content,
                provenance=c.provenance,
                kind="analysis",
            )
        )

    # --- retrieved lane ------------------------------------------------
    if retriever is not None:
        for hit in retriever.retrieve_for_source(question, sid, top_k=retrieved_k):
            ctx.retrieved_context.append(
                ContextItem(
                    ref=_ref(),
                    basis=Basis.RETRIEVED_KNOWLEDGE,
                    content=hit.chunk.content,
                    provenance=hit.provenance,
                    kind="retrieved",
                    score=round(hit.score, 6),
                )
            )

    return ctx
