"""
Quality-loop repair engine (Phase 11).

Drives a **single** propose -> validate attempt for one coherent
failure group per outer iteration (never the whole project, never every
unrelated failure at once). It deliberately does NOT decide confidence
or eligibility — those are computed first by
:mod:`app.quality_loop.eligibility` / :mod:`app.quality_loop.confidence`
and only an eligible, sufficiently-confident group ever reaches this
engine. It also does NOT apply the patch itself; application only
happens after the caller's confidence-gate / human-review decision, via
:func:`apply_repair` — a direct pass-through to #128's own
``apply_patch``.

Reuses #128's ``RepairPatch``/``parse_patch``/``validate_patch``/
``apply_patch`` unchanged. Zero duplication of the patch engine itself;
only the prompt and the grounded context differ for behavioral repairs
(#128 is compile-error-only).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMProviderError
from app.ai.providers.models import LLMRequest
from app.dataset.analysis_bundle import AnalysisBundle
from app.grounded.context import GroundedContext
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.errors import UnsafePatchError
from app.java_modernization.generation.models import GeneratedProject
from app.java_modernization.repair.loop import build_repair_prompt
from app.java_modernization.repair.models import RepairPatch
from app.java_modernization.repair.patch import apply_patch, parse_patch, validate_patch
from app.quality_loop.context import build_quality_repair_context
from app.quality_loop.failure import FailureCategory, FailureRecord

__all__ = [
    "QUALITY_REPAIR_PROMPT_VERSION",
    "build_behavioral_repair_prompt",
    "RepairProposalOutcome",
    "QualityRepairEngine",
    "apply_repair",
]

QUALITY_REPAIR_PROMPT_VERSION = "p11-behavioral-repair-prompt-v1"

_BEHAVIORAL_SYSTEM = """\
You repair generated Java so its observable BEHAVIOR matches the COBOL \
source it was generated from. You are given the failing test/behavioral \
evidence, the affected Java source, the COBOL it maps to, and the \
relevant business rules / IR.

Rules:
- Propose the SMALLEST edit that fixes the behavioral difference.
- Only edit the affected file(s) named in the evidence. Do not touch unrelated files.
- Do not remove the class/record declaration.
- Implement the COBOL business rule precisely — do not special-case the \
specific test input just to make one assertion pass.
- You do not run commands. You return a structured patch; the tool applies it.

Return ONE JSON object:
{
  "files": [
    {"path": "src/Foo.java",
     "changes": [{"start_line": 12, "end_line": 12, "replacement": "        foo();"}]}
  ],
  "explanation": "...",
  "source_basis": ["E1", "E4"]
}
"""


def build_behavioral_repair_prompt(context_text: str) -> str:
    return f"{_BEHAVIORAL_SYSTEM}\n\n# EVIDENCE\n{context_text}\n"


def _render_context(ctx: GroundedContext) -> str:
    blocks = []
    for it in ctx.all_items():
        blocks.append(f"[{it.ref}] ({it.basis.value}) {it.provenance.citation()}")
        blocks.append(it.content)
        blocks.append("")
    return "\n".join(blocks)


class RepairProposalOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    target_failure_ids: tuple[str, ...]
    context_refs: tuple[str, ...] = ()
    patch: RepairPatch | None = None
    validated: bool = False
    reject_reason: str | None = None
    provider_failed: bool = False
    provider_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json", exclude={"patch"})
        d["patch"] = self.patch.model_dump(mode="json") if self.patch else None
        return d


class QualityRepairEngine:
    """Proposes and mechanically validates one targeted patch per call.
    Never decides eligibility, confidence, or whether to apply."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> None:
        self._provider = provider
        self._temperature = temperature
        self._max_tokens = max_tokens

    def propose_repair(
        self,
        failures: tuple[FailureRecord, ...],
        *,
        project: GeneratedProject,
        bundle: AnalysisBundle,
        compilation: CompilationResult | None = None,
    ) -> RepairProposalOutcome:
        if not failures:
            raise ValueError("propose_repair requires at least one failure")
        category = failures[0].category
        failure_ids = tuple(f.failure_id for f in failures)

        ctx = build_quality_repair_context(
            failures, project=project, bundle=bundle, compilation=compilation
        )
        context_refs = tuple(ctx.by_ref().keys())

        prompt = (
            build_repair_prompt(_render_context(ctx))
            if category is FailureCategory.COMPILATION_ERROR
            else build_behavioral_repair_prompt(_render_context(ctx))
        )

        try:
            resp = self._provider.generate(
                LLMRequest(
                    prompt=prompt,
                    model=None,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
            )
        except LLMProviderError as exc:
            return RepairProposalOutcome(
                target_failure_ids=failure_ids,
                context_refs=context_refs,
                provider_failed=True,
                provider_error=str(exc),
            )

        patch = parse_patch(resp.text)
        if patch is None or patch.is_empty():
            return RepairProposalOutcome(
                target_failure_ids=failure_ids,
                context_refs=context_refs,
                reject_reason="unparseable_or_empty_patch",
            )

        allowed_files = {f.affected_artifact for f in failures if f.affected_artifact}
        if not allowed_files:
            return RepairProposalOutcome(
                target_failure_ids=failure_ids,
                context_refs=context_refs,
                patch=patch,
                reject_reason="no affected artifact known for this failure group",
            )

        try:
            validate_patch(patch, project, allowed_files=allowed_files)
        except UnsafePatchError as exc:
            return RepairProposalOutcome(
                target_failure_ids=failure_ids,
                context_refs=context_refs,
                patch=patch,
                reject_reason=f"unsafe_patch: {exc}",
            )

        return RepairProposalOutcome(
            target_failure_ids=failure_ids,
            context_refs=context_refs,
            patch=patch,
            validated=True,
        )


def apply_repair(patch: RepairPatch, project: GeneratedProject) -> GeneratedProject:
    """Direct pass-through to #128's ``apply_patch`` — application is a
    purely mechanical step performed only after the confidence-gate /
    human-review decision has been made."""
    return apply_patch(patch, project)
