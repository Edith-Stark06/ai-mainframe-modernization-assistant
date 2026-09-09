"""
#128 — the bounded, grounded self-repair loop.

    compile -> [ diagnostics -> grounded context -> LLM patch -> validate
                 -> apply -> compile -> record attempt ]  x max_attempts

Stops on: compiled OK · max_attempts reached · no progress (same
diagnostics) · duplicate patch · unsafe patch · provider failure.
The model proposes a structured patch; this loop validates and applies
it — the model never executes anything.
"""

from __future__ import annotations

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMProviderError
from app.ai.providers.models import LLMRequest
from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.compilation.compiler import JavaCompiler
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.errors import UnsafePatchError
from app.java_modernization.generation.models import GeneratedProject
from app.java_modernization.repair.context import build_repair_context
from app.java_modernization.repair.models import (
    RepairAttempt,
    RepairResult,
)
from app.java_modernization.repair.patch import apply_patch, parse_patch, validate_patch

__all__ = ["SelfRepairLoop", "REPAIR_PROMPT_VERSION", "build_repair_prompt"]

REPAIR_PROMPT_VERSION = "p9-repair-prompt-v1"

_SYSTEM = """\
You repair generated Java so it compiles. You are given the javac errors, \
the affected Java lines (numbered), the COBOL they map to, and the \
relevant business rules / IR.

Rules:
- Propose the SMALLEST edit that fixes the compiler errors.
- Only edit files that have a compiler error. Do not touch unrelated files.
- Do not remove the class/record declaration. Keep the COBOL behavior the \
generated code already expresses — a compile fix must not silently drop logic.
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


def build_repair_prompt(context_text: str) -> str:
    return f"{_SYSTEM}\n\n# EVIDENCE\n{context_text}\n"


def _render_context(ctx) -> str:  # type: ignore[no-untyped-def]
    blocks = []
    for it in ctx.all_items():
        blocks.append(f"[{it.ref}] ({it.basis.value}) {it.provenance.citation()}")
        blocks.append(it.content)
        blocks.append("")
    return "\n".join(blocks)


class SelfRepairLoop:
    def __init__(
        self,
        provider: LLMProvider,
        compiler: JavaCompiler,
        *,
        max_attempts: int = 3,
        temperature: float = 0.0,
        max_tokens: int = 1500,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._provider = provider
        self._compiler = compiler
        self._max_attempts = max_attempts
        self._temperature = temperature
        self._max_tokens = max_tokens

    def run(
        self,
        project: GeneratedProject,
        bundle: AnalysisBundle,
        *,
        initial_compilation: CompilationResult | None = None,
    ) -> RepairResult:
        comp = initial_compilation or self._compiler.compile(project)
        initial_errors = len(comp.errors)
        if comp.success:
            return RepairResult(
                success=True,
                stopped_reason="not_needed",
                initial_error_count=0,
                final_error_count=0,
                final_files=dict(project.files),
            )

        attempts: list[RepairAttempt] = []
        seen_patch_sigs: set[str] = set()
        seen_diag_sigs: set[str] = {comp.diagnostic_signature()}
        current = project

        for i in range(1, self._max_attempts + 1):
            ctx = build_repair_context(comp, current, bundle)
            affected_files = tuple(sorted({d.file for d in comp.errors if d.file}))
            affected_locs = tuple(
                d.cobol_source_mapping
                for d in comp.errors
                if d.cobol_source_mapping is not None
            )
            attempt = RepairAttempt(
                attempt_number=i,
                original_error_count=len(comp.errors),
                original_diagnostic_signature=comp.diagnostic_signature(),
                affected_files=affected_files,
                affected_source_locations=affected_locs,
                context_refs=tuple(ctx.by_ref().keys()),
            )

            # -- ask the model --------------------------------------
            try:
                resp = self._provider.generate(
                    LLMRequest(
                        prompt=build_repair_prompt(_render_context(ctx)),
                        model=None,
                        temperature=self._temperature,
                        max_tokens=self._max_tokens,
                    )
                )
            except LLMProviderError as exc:
                attempts.append(
                    attempt.model_copy(
                        update={
                            "note": f"provider_failure: {exc}",
                            "remaining_error_count": len(comp.errors),
                        }
                    )
                )
                return self._finish(
                    False, "provider_failure", attempts, initial_errors, comp, current
                )

            patch = parse_patch(resp.text)
            if patch is None or patch.is_empty():
                attempts.append(
                    attempt.model_copy(
                        update={
                            "reject_reason": "unparseable_or_empty_patch",
                            "remaining_error_count": len(comp.errors),
                        }
                    )
                )
                return self._finish(
                    False, "no_progress", attempts, initial_errors, comp, current
                )

            sig = patch.signature()
            if sig in seen_patch_sigs:
                attempts.append(
                    attempt.model_copy(
                        update={
                            "proposed_patch": patch,
                            "reject_reason": "duplicate_patch",
                            "remaining_error_count": len(comp.errors),
                        }
                    )
                )
                return self._finish(
                    False, "duplicate_patch", attempts, initial_errors, comp, current
                )
            seen_patch_sigs.add(sig)

            # -- validate + apply ----------------------------------
            try:
                validate_patch(patch, current, allowed_files=set(affected_files))
            except UnsafePatchError as exc:
                attempts.append(
                    attempt.model_copy(
                        update={
                            "proposed_patch": patch,
                            "reject_reason": f"unsafe_patch: {exc}",
                            "remaining_error_count": len(comp.errors),
                        }
                    )
                )
                return self._finish(
                    False, "unsafe_patch", attempts, initial_errors, comp, current
                )

            patched = apply_patch(patch, current)

            # -- recompile ----------------------------------------
            new_comp = self._compiler.compile(patched)
            attempts.append(
                attempt.model_copy(
                    update={
                        "proposed_patch": patch,
                        "patch_applied": True,
                        "compilation_result": new_comp,
                        "remaining_error_count": len(new_comp.errors),
                        "note": patch.explanation[:200],
                    }
                )
            )

            if new_comp.success:
                return self._finish(
                    True, "compiled", attempts, initial_errors, new_comp, patched
                )

            new_sig = new_comp.diagnostic_signature()
            if new_sig in seen_diag_sigs:
                return self._finish(
                    False, "no_progress", attempts, initial_errors, new_comp, patched
                )
            seen_diag_sigs.add(new_sig)
            comp, current = new_comp, patched

        return self._finish(
            False, "max_attempts", attempts, initial_errors, comp, current
        )

    @staticmethod
    def _finish(
        success: bool,
        reason: str,
        attempts: list[RepairAttempt],
        initial_errors: int,
        final_comp: CompilationResult,
        final_project: GeneratedProject,
    ) -> RepairResult:
        return RepairResult(
            success=success,
            stopped_reason=reason,
            attempts=tuple(attempts),
            initial_error_count=initial_errors,
            final_error_count=len(final_comp.errors),
            final_files=dict(final_project.files),
            semantic_equivalence_verified=False,
        )
