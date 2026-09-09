"""
#128 — build a *targeted*, provenance-carrying repair context.

Only the material relevant to the failing diagnostics is included:
the affected Java lines, their COBOL source mapping, the business rules
and IR for the affected paragraph, and the architecture component. Every
item is a Phase 8 :class:`~app.grounded.context.ContextItem` with a
validated :class:`~app.knowledge.provenance.Provenance`; anything without
provenance is not added.
"""

from __future__ import annotations

from app.dataset.analysis_bundle import AnalysisBundle
from app.grounded.context import Basis, ContextItem, GroundedContext
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.generation.models import GeneratedProject
from app.knowledge.chunkers import chunk_business_rules, chunk_ir
from app.knowledge.provenance import Provenance, SourceType
from app.knowledge.version import ANALYSIS_CONTRACT_VERSION

__all__ = ["build_repair_context"]

_WINDOW = 6


def build_repair_context(
    compilation: CompilationResult,
    project: GeneratedProject,
    bundle: AnalysisBundle,
) -> GroundedContext:
    ctx = GroundedContext(question="Fix the Java compilation errors below.")
    n = 0

    def ref() -> str:
        nonlocal n
        n += 1
        return f"E{n}"

    errors = compilation.errors
    affected_files = sorted({d.file for d in errors if d.file})
    affected_paras: set[str] = set()

    # --- diagnostics themselves (as evidence) -----------------------
    for d in errors:
        prov = Provenance(
            source_id=project.source_id,
            source_type=SourceType.GENERATED_JAVA,
            source_path=d.file,
            program_source_id=project.source_id,
            line_start=d.line,
            line_end=d.line,
            java_class=project.main_class,
            artifact_version=project.generation_version,
        )
        ctx.analysis_context.append(
            ContextItem(
                ref=ref(),
                basis=Basis.DETERMINISTIC_FACT,
                content=(
                    f"javac {d.severity.value}: {d.message}\n"
                    f"  at {d.file}:{d.line}"
                    + (
                        f"  (maps to {d.cobol_source_mapping.render()})"
                        if d.cobol_source_mapping
                        else ""
                    )
                ),
                provenance=prov,
                kind="analysis",
            )
        )
        if d.cobol_source_mapping and d.cobol_source_mapping.paragraph:
            affected_paras.add(d.cobol_source_mapping.paragraph.upper())

    # --- affected Java windows (source lane) ------------------------
    for fpath in affected_files:
        content = project.files.get(fpath, "")
        if not content:
            continue
        lines = content.splitlines()
        err_lines = sorted({d.line for d in errors if d.file == fpath and d.line})
        lo = max(1, min(err_lines) - _WINDOW)
        hi = min(len(lines), max(err_lines) + _WINDOW)
        snippet = "\n".join(f"{i:4}| {lines[i - 1]}" for i in range(lo, hi + 1))
        prov = Provenance(
            source_id=project.source_id,
            source_type=SourceType.GENERATED_JAVA,
            source_path=fpath,
            program_source_id=project.source_id,
            line_start=lo,
            line_end=hi,
            java_class=project.main_class,
            artifact_version=project.generation_version,
        )
        ctx.source_context.append(
            ContextItem(
                ref=ref(),
                basis=Basis.DETERMINISTIC_FACT,
                content=f"Affected generated Java ({fpath}):\n{snippet}",
                provenance=prov,
                kind="source",
            )
        )

    # --- relevant COBOL + rules + IR (analysis lane) ---------------
    src_lines = bundle.source.splitlines()
    for d in errors:
        sm = d.cobol_source_mapping
        if sm is None or sm.line_start is None:
            continue
        lo = max(1, sm.line_start - 2)
        hi = min(len(src_lines), (sm.line_end or sm.line_start) + 2)
        cobol = "\n".join(f"{i:4}| {src_lines[i - 1]}" for i in range(lo, hi + 1))
        ctx.analysis_context.append(
            ContextItem(
                ref=ref(),
                basis=Basis.DETERMINISTIC_FACT,
                content=f"COBOL source {sm.render()}:\n{cobol}",
                provenance=Provenance(
                    source_id=project.source_id,
                    source_type=SourceType.COBOL,
                    source_path=f"{project.source_id}.cbl",
                    program_source_id=project.source_id,
                    line_start=lo,
                    line_end=hi,
                    paragraph=sm.paragraph,
                    artifact_version=ANALYSIS_CONTRACT_VERSION,
                ),
                kind="analysis",
            )
        )

    rule_chunks = chunk_business_rules(
        bundle.business_rules,
        program_source_id=project.source_id,
        analysis_version=ANALYSIS_CONTRACT_VERSION,
    )
    all_rule_ids = {rid for d in errors for rid in d.business_rule_ids}
    for c in rule_chunks:
        if c.provenance.rule_id in all_rule_ids:
            ctx.analysis_context.append(
                ContextItem(
                    ref=ref(),
                    basis=Basis.DETERMINISTIC_FACT,
                    content=c.content,
                    provenance=c.provenance,
                    kind="analysis",
                )
            )

    if affected_paras:
        for c in chunk_ir(
            bundle.ir,
            program_source_id=project.source_id,
            analysis_version=ANALYSIS_CONTRACT_VERSION,
        ):
            if (c.provenance.paragraph or "").upper() in affected_paras:
                ctx.analysis_context.append(
                    ContextItem(
                        ref=ref(),
                        basis=Basis.DETERMINISTIC_FACT,
                        content=c.content,
                        provenance=c.provenance,
                        kind="analysis",
                    )
                )

    ctx.validate()  # hard boundary — nothing without provenance
    return ctx
