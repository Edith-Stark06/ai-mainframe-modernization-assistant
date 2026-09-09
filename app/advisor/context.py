"""
Task-specific context builders for the advisor (#124).

Each builder returns ``(GroundedContext, facts)`` where ``facts`` are the
deterministic Phase 1–5 statements the advisor is built on — the LLM is
asked to *explain / recommend*, never to rediscover them. Context is
scoped to the operation (no whole-repo dumps).
"""

from __future__ import annotations

from typing import Any

from app.dataset.analysis_bundle import AnalysisBundle
from app.advisor.models import Fact
from app.grounded.context import Basis, ContextItem, GroundedContext
from app.knowledge.chunkers import (
    chunk_business_rules,
    chunk_cfg,
    chunk_cobol_source,
    chunk_dependencies,
    chunk_generated_java,
    chunk_ir,
    chunk_risks,
    chunk_strategy,
)
from app.knowledge.provenance import Provenance, SourceType
from app.knowledge.retrieval import KnowledgeRetriever
from app.knowledge.version import ANALYSIS_CONTRACT_VERSION

__all__ = ["OperationContext", "build"]


class _Refs:
    def __init__(self) -> None:
        self.n = 0

    def next(self) -> str:
        self.n += 1
        return f"E{self.n}"


class OperationContext:
    def __init__(self, context: GroundedContext, facts: list[Fact]) -> None:
        self.context = context
        self.facts = facts


def _add(
    ctx: GroundedContext,
    refs: _Refs,
    lane: str,
    basis: Basis,
    chunks: list,  # type: ignore[type-arg]
) -> None:
    target = {
        "source": ctx.source_context,
        "analysis": ctx.analysis_context,
        "retrieved": ctx.retrieved_context,
    }[lane]
    for c in chunks:
        target.append(
            ContextItem(
                ref=refs.next(),
                basis=basis,
                content=c.content,
                provenance=c.provenance,
                kind=lane,
            )
        )


def _facts_from(chunks: list, prefix: str) -> list[Fact]:  # type: ignore[type-arg]
    out: list[Fact] = []
    for c in chunks:
        head = c.content.splitlines()[0] if c.content else prefix
        out.append(Fact(statement=head.strip(), provenance=c.provenance))
    return out


def build(
    operation: str,
    bundle: AnalysisBundle,
    *,
    paragraph: str | None = None,
    rule_id: str | None = None,
    question: str | None = None,
    retriever: KnowledgeRetriever | None = None,
    analysis_version: str = ANALYSIS_CONTRACT_VERSION,
) -> OperationContext:
    sid = bundle.source_id
    q = question or operation.replace("_", " ")
    ctx = GroundedContext(question=q)
    refs = _Refs()
    facts: list[Fact] = []

    src_chunks = chunk_cobol_source(
        sid, bundle.source, paragraph_names=list(bundle.paragraphs)
    )
    rules = chunk_business_rules(
        bundle.business_rules, program_source_id=sid, analysis_version=analysis_version
    )
    risks = chunk_risks(
        bundle.risks, program_source_id=sid, analysis_version=analysis_version
    )
    deps = chunk_dependencies(
        bundle.dependencies, program_source_id=sid, analysis_version=analysis_version
    )
    strat = chunk_strategy(
        bundle.strategy, program_source_id=sid, analysis_version=analysis_version
    )

    def paras(names: set[str] | None = None) -> list:  # type: ignore[type-arg]
        return [
            c
            for c in src_chunks
            if c.provenance.paragraph
            and (names is None or c.provenance.paragraph in names)
        ]

    if operation == "explain_paragraph":
        if not paragraph:
            raise ValueError("explain_paragraph requires a paragraph name")
        want = {paragraph.upper()}
        _add(ctx, refs, "source", Basis.DETERMINISTIC_FACT, paras(want))
        _add(
            ctx,
            refs,
            "analysis",
            Basis.DETERMINISTIC_FACT,
            chunk_ir(
                bundle.ir, program_source_id=sid, analysis_version=analysis_version
            ),
        )
        _add(
            ctx,
            refs,
            "analysis",
            Basis.DETERMINISTIC_FACT,
            [c for c in rules if _touches(c, want)]
            + [d for d in deps if (d.provenance.paragraph or "").upper() in want],
        )
        facts += _facts_from(paras(want), "paragraph")

    elif operation == "explain_business_rule":
        if not rule_id:
            raise ValueError("explain_business_rule requires a rule_id")
        target = [c for c in rules if c.provenance.rule_id == rule_id]
        if not target:
            ctx.analysis_context.append(
                _absent_item(refs, sid, f"business rule {rule_id}")
            )
        _add(ctx, refs, "analysis", Basis.DETERMINISTIC_FACT, target)
        rule_lines = {
            c.provenance.line_start
            for c in target
            if c.provenance.line_start is not None
        }
        _add(
            ctx,
            refs,
            "source",
            Basis.DETERMINISTIC_FACT,
            [
                c
                for c in paras()
                if c.provenance.line_start is not None
                and any(
                    c.provenance.line_start <= ln <= (c.provenance.line_end or ln)
                    for ln in rule_lines
                )
            ],
        )
        facts += _facts_from(target, "rule")

    elif operation == "identify_risks":
        _add(ctx, refs, "analysis", Basis.DETERMINISTIC_FACT, risks)
        _add(ctx, refs, "source", Basis.DETERMINISTIC_FACT, paras())
        facts += _facts_from(risks, "risk")

    elif operation == "recommend_strategy":
        _add(
            ctx,
            refs,
            "analysis",
            Basis.DETERMINISTIC_FACT,
            strat + risks + rules + deps,
        )
        facts += _facts_from(strat + risks, "strategy")

    elif operation == "explain_dependencies":
        _add(ctx, refs, "analysis", Basis.DETERMINISTIC_FACT, deps)
        _add(
            ctx,
            refs,
            "analysis",
            Basis.DETERMINISTIC_FACT,
            chunk_cfg(
                bundle.cfg, program_source_id=sid, analysis_version=analysis_version
            ),
        )
        facts += _facts_from(deps, "dependency")

    elif operation in ("propose_java_architecture", "review_generated_java"):
        java = chunk_generated_java(bundle.java_backend_output, program_source_id=sid)
        _add(ctx, refs, "retrieved", Basis.DETERMINISTIC_FACT, java)
        _add(
            ctx,
            refs,
            "analysis",
            Basis.DETERMINISTIC_FACT,
            chunk_ir(
                bundle.ir, program_source_id=sid, analysis_version=analysis_version
            )
            + rules
            + deps,
        )
        _add(ctx, refs, "source", Basis.DETERMINISTIC_FACT, paras())
        facts += _facts_from(java, "java") + _facts_from(rules, "rule")

    else:  # explain_program, answer_migration_question
        _add(ctx, refs, "source", Basis.DETERMINISTIC_FACT, paras())
        _add(
            ctx,
            refs,
            "analysis",
            Basis.DETERMINISTIC_FACT,
            rules + risks + strat + deps,
        )
        facts += _facts_from(rules + risks, "analysis")

    if retriever is not None:
        for hit in retriever.retrieve_for_source(q, sid, top_k=4):
            ctx.retrieved_context.append(
                ContextItem(
                    ref=refs.next(),
                    basis=Basis.RETRIEVED_KNOWLEDGE,
                    content=hit.chunk.content,
                    provenance=hit.provenance,
                    kind="retrieved",
                    score=round(hit.score, 6),
                )
            )

    return OperationContext(ctx, facts)


def _touches(chunk: Any, para_names: set[str]) -> bool:
    text = chunk.content.upper()
    return any(p in text for p in para_names)


def _absent_item(refs: _Refs, source_id: str, what: str) -> ContextItem:
    return ContextItem(
        ref=refs.next(),
        basis=Basis.DETERMINISTIC_FACT,
        content=f"The deterministic analysis of {source_id} contains no {what}.",
        provenance=Provenance(
            source_id=source_id,
            source_type=SourceType.AST,
            program_source_id=source_id,
            artifact_version=ANALYSIS_CONTRACT_VERSION,
            analysis_version=ANALYSIS_CONTRACT_VERSION,
        ),
        kind="analysis",
    )
