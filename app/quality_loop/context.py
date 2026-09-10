"""
Grounded repair context builders (Phase 11).

For ``COMPILATION_ERROR`` failures this is a thin wrapper around #128's
own :func:`app.java_modernization.repair.context.build_repair_context`
— zero duplication of that engine. For ``TEST_FAILURE`` /
``EXECUTION_FAILURE`` / ``BEHAVIORAL_MISMATCH`` failures (which #128 has
no notion of at all, being compile-only) this module builds an
equivalent, equally provenance-checked context from the normalized
:class:`~app.quality_loop.failure.FailureRecord` evidence, reusing the
exact same Phase 8 primitives (`GroundedContext`, `ContextItem`,
`Basis`, `Provenance`) #128 uses.

Every item keeps provenance. If a failure has no source mapping,
:func:`app.quality_loop.eligibility.repair_eligibility` already refused
it before this module is ever reached — ``GroundedContext.validate()``
is the second, hard boundary that would catch any regression of that
invariant.
"""

from __future__ import annotations

from app.dataset.analysis_bundle import AnalysisBundle
from app.grounded.context import Basis, ContextItem, GroundedContext
from app.java_modernization.compilation.models import (
    CompilationResult,
    DiagnosticSeverity,
)
from app.java_modernization.generation.models import GeneratedProject
from app.java_modernization.repair.context import build_repair_context
from app.knowledge.chunkers import chunk_business_rules, chunk_ir
from app.knowledge.provenance import Provenance, SourceType
from app.knowledge.version import ANALYSIS_CONTRACT_VERSION
from app.quality_loop.failure import FailureCategory, FailureRecord

__all__ = [
    "build_compilation_repair_context",
    "build_behavioral_repair_context",
    "build_quality_repair_context",
]


def _filtered_compilation_for_group(
    compilation: CompilationResult, failures: tuple[FailureRecord, ...]
) -> CompilationResult:
    """Restrict a full :class:`CompilationResult` to just the diagnostics
    that produced this failure group, so #128's context builder only sees
    the one coherent group Phase 11 is currently repairing."""
    keys = {(f.affected_artifact, f.message) for f in failures}
    kept = tuple(
        d
        for d in compilation.diagnostics
        if d.severity is DiagnosticSeverity.ERROR and (d.file, d.message) in keys
    )
    return compilation.model_copy(update={"diagnostics": kept, "success": False})


def build_compilation_repair_context(
    failures: tuple[FailureRecord, ...],
    compilation: CompilationResult,
    project: GeneratedProject,
    bundle: AnalysisBundle,
) -> GroundedContext:
    """Reuses #128's ``build_repair_context`` directly -- no duplication."""
    scoped = _filtered_compilation_for_group(compilation, failures)
    return build_repair_context(scoped, project, bundle)


def build_behavioral_repair_context(
    failures: tuple[FailureRecord, ...],
    project: GeneratedProject,
    bundle: AnalysisBundle,
) -> GroundedContext:
    """New for Phase 11: a grounded context for TEST_FAILURE / EXECUTION_FAILURE /
    BEHAVIORAL_MISMATCH failures, mirroring #128's structure but sourced from
    behavioral evidence instead of compiler diagnostics.

    Compiler diagnostics carry a precise Java *line*; behavioral evidence
    does not, so the affected Java artifact is included in full rather than
    windowed -- still targeted to only the affected file(s), never the
    whole project.
    """
    ctx = GroundedContext(
        question="Fix the generated Java so its behavior matches the COBOL "
        "source for the failure(s) below."
    )
    n = 0

    def ref() -> str:
        nonlocal n
        n += 1
        return f"E{n}"

    affected_paras: set[str] = set()
    affected_files: set[str] = set()
    all_rule_ids: set[str] = set()

    # --- the failure evidence itself ---------------------------------
    for f in failures:
        sm = f.source_mapping
        prov = Provenance(
            source_id=project.source_id,
            source_type=SourceType.GENERATED_JAVA,
            source_path=f.affected_artifact,
            program_source_id=project.source_id,
            line_start=sm.line_start if sm else None,
            line_end=sm.line_end if sm else None,
            java_class=project.main_class,
            artifact_version=project.generation_version,
        )
        ctx.analysis_context.append(
            ContextItem(
                ref=ref(),
                basis=Basis.DETERMINISTIC_FACT,
                content=(
                    f"{f.category.value}: {f.message}\n"
                    f"  evidence: {'; '.join(f.evidence) or '(none)'}"
                    + (f"\n  maps to {sm.render()}" if sm else "")
                ),
                provenance=prov,
                kind="analysis",
            )
        )
        if f.affected_artifact:
            affected_files.add(f.affected_artifact)
        if sm and sm.paragraph:
            affected_paras.add(sm.paragraph.upper())
        all_rule_ids.update(f.business_rule_ids)

    # --- affected Java source (source lane; full file -- no line to window on) ---
    for fpath in sorted(affected_files):
        content = project.files.get(fpath, "")
        if not content:
            continue
        numbered = "\n".join(
            f"{i:4}| {line}" for i, line in enumerate(content.splitlines(), start=1)
        )
        prov = Provenance(
            source_id=project.source_id,
            source_type=SourceType.GENERATED_JAVA,
            source_path=fpath,
            program_source_id=project.source_id,
            line_start=1,
            line_end=len(content.splitlines()),
            java_class=project.main_class,
            artifact_version=project.generation_version,
        )
        ctx.source_context.append(
            ContextItem(
                ref=ref(),
                basis=Basis.DETERMINISTIC_FACT,
                content=f"Affected generated Java ({fpath}):\n{numbered}",
                provenance=prov,
                kind="source",
            )
        )

    # --- relevant COBOL (analysis lane) -------------------------------
    src_lines = bundle.source.splitlines()
    for f in failures:
        sm = f.source_mapping
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

    # --- business rules + IR (analysis lane) --------------------------
    rule_chunks = chunk_business_rules(
        bundle.business_rules,
        program_source_id=project.source_id,
        analysis_version=ANALYSIS_CONTRACT_VERSION,
    )
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


def build_quality_repair_context(
    failures: tuple[FailureRecord, ...],
    *,
    project: GeneratedProject,
    bundle: AnalysisBundle,
    compilation: CompilationResult | None = None,
) -> GroundedContext:
    """Dispatch to the right context builder for this (already-grouped,
    single-category) failure group."""
    if not failures:
        raise ValueError("build_quality_repair_context requires at least one failure")
    category = failures[0].category
    if any(f.category != category for f in failures):
        raise ValueError("a repair context group must share one failure category")

    if category is FailureCategory.COMPILATION_ERROR:
        if compilation is None:
            raise ValueError("COMPILATION_ERROR repair context requires `compilation`")
        return build_compilation_repair_context(failures, compilation, project, bundle)

    if category in (
        FailureCategory.TEST_FAILURE,
        FailureCategory.EXECUTION_FAILURE,
        FailureCategory.BEHAVIORAL_MISMATCH,
    ):
        return build_behavioral_repair_context(failures, project, bundle)

    raise ValueError(f"{category.value} has no repair context builder (not repairable)")
