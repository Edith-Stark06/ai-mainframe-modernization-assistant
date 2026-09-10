"""
Phase 11 orchestrator — the quality loop itself.

    iteration 0: Analyze (reused) -> Generate (reused) -> Compile -> Test
                 -> Compare -> {PASS -> COMPLETED;
                                INCONCLUSIVE-only -> STOPPED;
                                failures -> evaluate repair -> confidence
                                gate -> AI repair -> validate -> apply ->
                                recompile -> retest -> recompare ->
                                iteration 1 -> ...}

The deterministic pipeline (#125-#131) stays authoritative throughout;
this module only adds the bounded control loop around it. AI is invoked
exactly once per iteration, only for the single highest-priority,
already-eligible failure group, and only after deterministic evidence
identified that failure — never to decide whether modernization is
correct.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.ai.providers.base import LLMProvider
from app.behavioral.comparison.models import ComparisonStatus, Phase10Report
from app.behavioral.execution.base import ProgramExecutor
from app.behavioral.extraction.extractor import extract_behavioral_tests
from app.behavioral.javatests import JavaTestRunner
from app.behavioral.javatests.models import JavaTestSuiteResult
from app.behavioral.orchestrator import run_behavioral_validation
from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.architecture.models import JavaArchitecture
from app.java_modernization.compilation.compiler import JavaCompiler
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.generation.models import GeneratedProject
from app.quality_loop.audit import AuditEventType, AuditLog
from app.quality_loop.candidate import first_candidate, next_candidate
from app.quality_loop.confidence import (
    ConfidenceAction,
    compute_confidence,
    decide_confidence_action,
    factors_from_failure_group,
)
from app.quality_loop.eligibility import repair_eligibility
from app.quality_loop.failure import (
    FailureCategory,
    classify_failures,
    group_failures,
)
from app.quality_loop.models import (
    FinalStatus,
    LoopState,
    QualityIteration,
    QualityLoop,
    QualityLoopConfig,
    RepairOutcome,
    RepairProposalRecord,
    StopReason,
)
from app.quality_loop.repair_engine import QualityRepairEngine, apply_repair
from app.quality_loop.review import HumanReviewBoard, HumanReviewCheckpoint

__all__ = ["run_quality_loop"]


def _default_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash8(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:8]


def _comparison_signature(report: Phase10Report | None) -> str:
    """Value-based, not just status-based: two FAILs with a *different*
    observed value are NOT the same "identical behavioral difference"."""
    if report is None:
        return "none"
    parts: list[str] = []
    for c in sorted(report.comparisons, key=lambda c: c.test_id):
        if c.status is ComparisonStatus.FAIL and c.differences:
            for d in c.differences:
                parts.append(f"{c.test_id}:{d.field}:{d.cobol_value}:{d.java_value}")
        else:
            parts.append(f"{c.test_id}:{c.status.value}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _test_signature(result: JavaTestSuiteResult | None) -> str:
    """Value-based, not just pass/fail: two failing runs with *different*
    observed field values are NOT the same "identical" failure."""
    if result is None:
        return "none"
    parts: list[str] = []
    for r in sorted(result.runs, key=lambda r: r.test_id):
        values = "|".join(f"{k}={v}" for k, v in sorted(r.field_values.items()))
        stdout = "|".join(r.stdout_lines)
        parts.append(
            f"{r.test_id}:{r.execution_ok}:{r.assertion_passed}:{values}:{stdout}:"
            f"{sorted(r.failed_fields)}"
        )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _is_clean(
    compilation: CompilationResult,
    test_result: JavaTestSuiteResult | None,
    report: Phase10Report | None,
) -> bool:
    if not compilation.success:
        return False
    if test_result is not None and any(
        (not r.execution_ok) or r.assertion_passed is False for r in test_result.runs
    ):
        return False
    if report is not None and (report.fail_count > 0 or report.inconclusive_count > 0):
        return False
    return True


def _regressions(
    before: Phase10Report | None, after: Phase10Report | None
) -> tuple[str, ...]:
    if before is None or after is None:
        return ()
    before_status = {c.test_id: c.status for c in before.comparisons}
    return tuple(
        c.test_id
        for c in after.comparisons
        if before_status.get(c.test_id) is ComparisonStatus.PASS
        and c.status is ComparisonStatus.FAIL
    )


def _repair_outcome(
    *,
    before_errors: int,
    after_errors: int,
    before_bad: int,
    after_bad: int,
    regressed: tuple[str, ...],
) -> RepairOutcome:
    if regressed:
        return RepairOutcome.REGRESSION
    before_total, after_total = before_errors + before_bad, after_errors + after_bad
    if after_total == 0 and before_total > 0:
        return RepairOutcome.PASS
    if after_total < before_total:
        return RepairOutcome.PARTIAL_IMPROVEMENT
    return RepairOutcome.NO_CHANGE


def run_quality_loop(
    bundle: AnalysisBundle,
    architecture: JavaArchitecture,
    project: GeneratedProject,
    *,
    workspace_root: str | Path,
    compiler: JavaCompiler,
    provider: LLMProvider,
    modernization_id: str,
    config: QualityLoopConfig | None = None,
    cobol_executor: ProgramExecutor | None = None,
    java_executor: ProgramExecutor | None = None,
    now: Callable[[], str] | None = None,
) -> tuple[QualityLoop, HumanReviewBoard]:
    cfg = config or QualityLoopConfig()
    clock = now or _default_now
    started_monotonic = time.monotonic()

    suite = extract_behavioral_tests(bundle)
    candidate = first_candidate(
        bundle=bundle, architecture=architecture, project=project, test_suite=suite
    )
    loop_id = f"loop-{_hash8(modernization_id, candidate.candidate_id)}"
    audit = AuditLog(loop_id=loop_id)
    board = HumanReviewBoard()
    engine = QualityRepairEngine(provider)
    test_runner = JavaTestRunner(workspace_root)

    loop = QualityLoop(
        loop_id=loop_id,
        modernization_id=modernization_id,
        configuration=cfg,
        current_candidate=candidate,
        audit_log=audit,
    )

    def _audit(
        *,
        iteration_number: int,
        event_type: AuditEventType,
        actor: str,
        input_refs: tuple[str, ...] = (),
        output_refs: tuple[str, ...] = (),
        decision: str = "",
        reason: str = "",
    ) -> None:
        nonlocal loop
        loop = loop.with_audit_log(
            loop.audit_log.append(
                timestamp=clock(),
                iteration_number=iteration_number,
                event_type=event_type,
                actor=actor,
                input_refs=input_refs,
                output_refs=output_refs,
                decision=decision,
                reason=reason,
            )
        )

    def _finish(
        *,
        final_status: FinalStatus,
        stop_reason: StopReason | None,
        human_review_required: bool,
        loop_state: LoopState,
        iteration_number: int,
        reason: str,
    ) -> tuple[QualityLoop, HumanReviewBoard]:
        nonlocal loop
        loop = loop.transition(loop_state)
        loop = loop.finish(
            final_status=final_status,
            stop_reason=stop_reason,
            human_review_required=human_review_required,
        )
        _audit(
            iteration_number=iteration_number,
            event_type=(
                AuditEventType.LOOP_COMPLETED
                if loop_state is LoopState.COMPLETED
                else AuditEventType.LOOP_STOPPED
            ),
            actor="quality_loop",
            decision=f"{final_status.value}"
            + (f"/{stop_reason.value}" if stop_reason else ""),
            reason=reason,
        )
        return loop, board

    _audit(
        iteration_number=0,
        event_type=AuditEventType.ANALYSIS_STARTED,
        actor="quality_loop",
        input_refs=(bundle.source_id,),
    )
    _audit(
        iteration_number=0,
        event_type=AuditEventType.ANALYSIS_COMPLETED,
        actor="quality_loop",
        output_refs=(bundle.source_id,),
    )
    loop = loop.transition(LoopState.GENERATING)
    _audit(
        iteration_number=0,
        event_type=AuditEventType.GENERATION_STARTED,
        actor="quality_loop",
        input_refs=(architecture.content_hash(),),
    )
    _audit(
        iteration_number=0,
        event_type=AuditEventType.GENERATION_COMPLETED,
        actor="quality_loop",
        output_refs=(project.content_hash(),),
    )
    loop = loop.transition(LoopState.COMPILING)

    current_project = project
    seen_diag_sigs: set[str] = set()
    seen_cmp_sigs: set[str] = set()
    seen_test_sigs: set[str] = set()
    seen_patch_sigs: set[str] = set()
    seen_project_hashes: set[str] = set()
    total_repairs_applied = 0

    for iteration_number in range(cfg.max_iterations):
        if (
            cfg.max_runtime_s is not None
            and (time.monotonic() - started_monotonic) > cfg.max_runtime_s
        ):
            return _finish(
                final_status=FinalStatus.STOPPED,
                stop_reason=StopReason.TIMEOUT,
                human_review_required=False,
                loop_state=LoopState.STOPPED,
                iteration_number=iteration_number,
                reason=f"exceeded max_runtime_s={cfg.max_runtime_s}",
            )

        # ---- COMPILE ------------------------------------------------
        _audit(
            iteration_number=iteration_number,
            event_type=AuditEventType.COMPILATION_STARTED,
            actor="quality_loop",
            input_refs=(current_project.content_hash(),),
        )
        comp = compiler.compile(current_project)
        _audit(
            iteration_number=iteration_number,
            event_type=AuditEventType.COMPILATION_COMPLETED,
            actor="quality_loop",
            output_refs=(comp.diagnostic_signature(),),
            decision="success" if comp.success else "failed",
        )

        test_result: JavaTestSuiteResult | None = None
        report: Phase10Report | None = None

        if comp.success:
            loop = loop.transition(LoopState.TESTING)
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.TEST_STARTED,
                actor="quality_loop",
            )
            test_result = test_runner.run_suite(suite, current_project)
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.TEST_COMPLETED,
                actor="quality_loop",
                output_refs=(_test_signature(test_result),),
            )

            loop = loop.transition(LoopState.COMPARING)
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.COMPARISON_STARTED,
                actor="quality_loop",
            )
            report = run_behavioral_validation(
                bundle,
                architecture,
                current_project,
                workspace_root=workspace_root,
                cobol_executor=cobol_executor,
                java_executor=java_executor,
            )
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.COMPARISON_COMPLETED,
                actor="quality_loop",
                output_refs=(_comparison_signature(report),),
                decision=report.overall_status.value,
            )

        failures = classify_failures(
            compilation=comp,
            java_tests=test_result,
            behavioral=report,
            project=current_project,
        )

        # ---- CLEAN: nothing failed, nothing inconclusive -------------
        if not failures:
            loop = loop.record_iteration(
                QualityIteration(
                    iteration_number=iteration_number,
                    candidate_id=loop.current_candidate.candidate_id,
                    state=LoopState.COMPARING,
                    analysis_result=bundle.source_id,
                    generated_artifacts=current_project.content_hash(),
                    compilation_result=comp,
                    test_result=test_result,
                    comparison_result=report,
                    decision="PASS: all gates satisfied",
                    timestamp=clock(),
                )
            )
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.ITERATION_COMPLETED,
                actor="quality_loop",
                decision="PASS",
            )
            return _finish(
                final_status=FinalStatus.PASS,
                stop_reason=None,
                human_review_required=False,
                loop_state=LoopState.COMPLETED,
                iteration_number=iteration_number,
                reason="compilation, tests and behavioral comparison all passed",
            )

        top_category = failures[0].category
        _audit(
            iteration_number=iteration_number,
            event_type=AuditEventType.FAILURE_DETECTED,
            actor="quality_loop",
            output_refs=tuple(f.failure_id for f in failures),
            decision=top_category.value,
            reason=failures[0].message,
        )
        loop = loop.transition(LoopState.FAILURE_DETECTED)

        def _record_and_stop(
            *,
            final_status: FinalStatus,
            stop_reason: StopReason | None,
            loop_state: LoopState,
            reason: str,
            decision: str,
            checkpoint_reason: str | None = None,
            repair_attempt: RepairProposalRecord | None = None,
        ) -> tuple[QualityLoop, HumanReviewBoard]:
            nonlocal loop, board
            loop = loop.record_iteration(
                QualityIteration(
                    iteration_number=iteration_number,
                    candidate_id=loop.current_candidate.candidate_id,
                    state=loop.state,
                    analysis_result=bundle.source_id,
                    generated_artifacts=current_project.content_hash(),
                    compilation_result=comp,
                    test_result=test_result,
                    comparison_result=report,
                    failures=failures,
                    repair_attempt=repair_attempt,
                    decision=decision,
                    timestamp=clock(),
                )
            )
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.ITERATION_COMPLETED,
                actor="quality_loop",
                decision=decision,
            )
            if checkpoint_reason is not None:
                checkpoint = HumanReviewCheckpoint(
                    checkpoint_id=f"chk-{_hash8(loop.loop_id, str(iteration_number), checkpoint_reason)}",
                    loop_id=loop.loop_id,
                    iteration_number=iteration_number,
                    reason=checkpoint_reason,
                    evidence=tuple(f.message for f in failures),
                    proposed_action="none",
                )
                board = board.open_checkpoint(checkpoint)
                _audit(
                    iteration_number=iteration_number,
                    event_type=AuditEventType.HUMAN_REVIEW_REQUESTED,
                    actor="quality_loop",
                    output_refs=(checkpoint.checkpoint_id,),
                    reason=checkpoint_reason,
                )
            return _finish(
                final_status=final_status,
                stop_reason=stop_reason,
                human_review_required=checkpoint_reason is not None,
                loop_state=loop_state,
                iteration_number=iteration_number,
                reason=reason,
            )

        # ---- SAFETY-FIRST: provenance/infrastructure gaps -----------
        if top_category in (
            FailureCategory.PROVENANCE_FAILURE,
            FailureCategory.INFRASTRUCTURE_FAILURE,
        ):
            return _record_and_stop(
                final_status=FinalStatus.HUMAN_REVIEW,
                stop_reason=(
                    StopReason.INFRASTRUCTURE_FAILURE
                    if top_category is FailureCategory.INFRASTRUCTURE_FAILURE
                    else None
                ),
                loop_state=LoopState.HUMAN_REVIEW,
                reason=f"{top_category.value} blocks any further automated action",
                decision=f"HUMAN_REVIEW: {top_category.value}",
                checkpoint_reason=f"{top_category.value}: {failures[0].message}",
            )

        # ---- nothing left but unsupported semantics ------------------
        if top_category is FailureCategory.UNSUPPORTED_BEHAVIOR:
            return _record_and_stop(
                final_status=FinalStatus.INCONCLUSIVE,
                stop_reason=StopReason.NO_ELIGIBLE_REPAIR,
                loop_state=LoopState.STOPPED,
                reason="only UNSUPPORTED_BEHAVIOR failures remain; behavior cannot be verified",
                decision="INCONCLUSIVE: unsupported COBOL semantics",
                checkpoint_reason=f"unsupported behavior: {failures[0].message}",
            )

        # ---- pick one coherent, highest-priority group ---------------
        same_category = tuple(f for f in failures if f.category is top_category)
        group = group_failures(same_category)[0]

        eligibility = [repair_eligibility(f) for f in group]
        eligible = all(ok for ok, _ in eligibility)
        if not eligible:
            reason_text = next(msg for ok, msg in eligibility if not ok)
            return _record_and_stop(
                final_status=(
                    FinalStatus.INCONCLUSIVE
                    if top_category is FailureCategory.BEHAVIORAL_MISMATCH
                    else FinalStatus.FAIL
                ),
                stop_reason=StopReason.NO_ELIGIBLE_REPAIR,
                loop_state=LoopState.HUMAN_REVIEW,
                reason=reason_text,
                decision=f"HUMAN_REVIEW: not eligible ({reason_text})",
                checkpoint_reason=reason_text,
            )

        if total_repairs_applied >= cfg.max_total_repairs:
            return _record_and_stop(
                final_status=FinalStatus.FAIL,
                stop_reason=StopReason.REPAIR_BUDGET_EXHAUSTED,
                loop_state=LoopState.STOPPED,
                reason="max_total_repairs exhausted; failure evidence stands as verified FAIL",
                decision="FAIL: repair budget exhausted",
            )

        factors = factors_from_failure_group(group, context_complete=True)
        score = compute_confidence(factors)
        action, action_reason = decide_confidence_action(score.value, cfg)

        if action is ConfidenceAction.NO_PATCH_PROPOSE:
            return _record_and_stop(
                final_status=FinalStatus.HUMAN_REVIEW,
                stop_reason=None,
                loop_state=LoopState.HUMAN_REVIEW,
                reason=action_reason,
                decision=f"HUMAN_REVIEW: {action_reason}",
                checkpoint_reason=action_reason,
            )

        # ---- propose + mechanically validate one targeted patch ------
        _audit(
            iteration_number=iteration_number,
            event_type=AuditEventType.REPAIR_REQUESTED,
            actor="quality_loop",
            input_refs=tuple(f.failure_id for f in group),
            decision=f"confidence={score.value:.2f}",
        )
        outcome = engine.propose_repair(
            group,
            project=current_project,
            bundle=bundle,
            compilation=(
                comp if top_category is FailureCategory.COMPILATION_ERROR else None
            ),
        )

        if outcome.provider_failed or not outcome.validated:
            reason_text = outcome.provider_error or outcome.reject_reason or "unknown"
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.REPAIR_REJECTED,
                actor="ai_provider" if outcome.patch else "quality_loop",
                reason=reason_text,
            )
            return _record_and_stop(
                final_status=FinalStatus.HUMAN_REVIEW,
                stop_reason=StopReason.REPAIR_REJECTED,
                loop_state=LoopState.HUMAN_REVIEW,
                reason=f"repair proposal rejected: {reason_text}",
                decision=f"HUMAN_REVIEW: repair rejected ({reason_text})",
                checkpoint_reason=f"repair rejected: {reason_text}",
            )

        patch = outcome.patch
        assert patch is not None
        patch_sig = patch.signature()
        _audit(
            iteration_number=iteration_number,
            event_type=AuditEventType.REPAIR_PROPOSED,
            actor="ai_provider",
            input_refs=outcome.context_refs,
            output_refs=(patch_sig,),
            decision=f"confidence={score.value:.2f}",
            reason=patch.explanation[:200],
        )

        if patch_sig in seen_patch_sigs:
            return _record_and_stop(
                final_status=FinalStatus.STOPPED,
                stop_reason=StopReason.NO_PROGRESS,
                loop_state=LoopState.STOPPED,
                reason="identical repair patch proposed again",
                decision="STOPPED: NO_PROGRESS (duplicate patch)",
            )
        seen_patch_sigs.add(patch_sig)
        loop = loop.transition(LoopState.REPAIR_PROPOSED)

        # re-fold the post-hoc "patch was structurally valid" evidence factor
        factors2 = factors.model_copy(update={"patch_structurally_valid": True})
        score2 = compute_confidence(factors2)
        action2, action_reason2 = decide_confidence_action(score2.value, cfg)

        if action2 is not ConfidenceAction.AUTO_APPLY:
            proposal = RepairProposalRecord(
                target_failure_ids=outcome.target_failure_ids,
                patch_signature=patch_sig,
                confidence=score2.value,
                confidence_label=score2.label,
                eligible=True,
                eligibility_reason="eligible",
                validated=True,
                applied=False,
                requires_human_review=True,
                explanation=patch.explanation,
                source_basis=patch.source_basis,
            )
            loop = loop.record_iteration(
                QualityIteration(
                    iteration_number=iteration_number,
                    candidate_id=loop.current_candidate.candidate_id,
                    state=LoopState.REPAIR_PROPOSED,
                    analysis_result=bundle.source_id,
                    generated_artifacts=current_project.content_hash(),
                    compilation_result=comp,
                    test_result=test_result,
                    comparison_result=report,
                    failures=failures,
                    repair_attempt=proposal,
                    confidence=score2.value,
                    decision=f"HUMAN_REVIEW: {action_reason2}",
                    timestamp=clock(),
                )
            )
            checkpoint = HumanReviewCheckpoint(
                checkpoint_id=f"chk-{_hash8(loop.loop_id, str(iteration_number), patch_sig)}",
                loop_id=loop.loop_id,
                iteration_number=iteration_number,
                reason=action_reason2,
                evidence=tuple(f.message for f in group),
                proposed_action=patch.explanation,
            )
            board = board.open_checkpoint(checkpoint)
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.HUMAN_REVIEW_REQUESTED,
                actor="quality_loop",
                output_refs=(checkpoint.checkpoint_id,),
                reason=action_reason2,
            )
            _audit(
                iteration_number=iteration_number,
                event_type=AuditEventType.ITERATION_COMPLETED,
                actor="quality_loop",
                decision=f"HUMAN_REVIEW: {action_reason2}",
            )
            return _finish(
                final_status=FinalStatus.HUMAN_REVIEW,
                stop_reason=None,
                human_review_required=True,
                loop_state=LoopState.HUMAN_REVIEW,
                iteration_number=iteration_number,
                reason=action_reason2,
            )

        # ---- AUTO_APPLY: apply, recompile, retest, recompare ---------
        loop = loop.transition(LoopState.REPAIR_VALIDATED)
        patched_project = apply_repair(patch, current_project)
        _audit(
            iteration_number=iteration_number,
            event_type=AuditEventType.REPAIR_APPLIED,
            actor="quality_loop",
            output_refs=(patched_project.content_hash(),),
        )

        recomp = compiler.compile(patched_project)
        retest = (
            test_runner.run_suite(suite, patched_project) if recomp.success else None
        )
        recompare = (
            run_behavioral_validation(
                bundle,
                architecture,
                patched_project,
                workspace_root=workspace_root,
                cobol_executor=cobol_executor,
                java_executor=java_executor,
            )
            if recomp.success
            else None
        )

        before_errors, after_errors = len(comp.errors), len(recomp.errors)
        before_bad = (
            (report.fail_count + report.inconclusive_count) if report else 0
        ) + (
            sum(
                1
                for r in test_result.runs
                if r.assertion_passed is False or not r.execution_ok
            )
            if test_result
            else 0
        )
        after_bad = (
            (recompare.fail_count + recompare.inconclusive_count) if recompare else 0
        ) + (
            sum(
                1
                for r in retest.runs
                if r.assertion_passed is False or not r.execution_ok
            )
            if retest
            else 0
        )
        regressed = _regressions(report, recompare)
        repair_outcome = _repair_outcome(
            before_errors=before_errors,
            after_errors=after_errors,
            before_bad=before_bad,
            after_bad=after_bad,
            regressed=regressed,
        )
        total_repairs_applied += 1

        proposal = RepairProposalRecord(
            target_failure_ids=outcome.target_failure_ids,
            patch_signature=patch_sig,
            confidence=score2.value,
            confidence_label=score2.label,
            eligible=True,
            eligibility_reason="eligible",
            validated=True,
            applied=True,
            requires_human_review=False,
            outcome=repair_outcome,
            before_metrics={"errors": before_errors, "behavioral_bad": before_bad},
            after_metrics={"errors": after_errors, "behavioral_bad": after_bad},
            explanation=patch.explanation,
            source_basis=patch.source_basis,
        )

        if repair_outcome is RepairOutcome.REGRESSION:
            return _record_and_stop(
                final_status=FinalStatus.HUMAN_REVIEW,
                stop_reason=StopReason.REPAIR_REJECTED,
                loop_state=LoopState.HUMAN_REVIEW,
                reason=f"repair caused a regression in {regressed}; candidate not accepted",
                decision="HUMAN_REVIEW: REGRESSION",
                checkpoint_reason=f"repair regressed previously-passing test(s): {regressed}",
                repair_attempt=proposal,
            )

        # record this iteration's repair (whether or not it fully fixed things)
        loop = loop.record_iteration(
            QualityIteration(
                iteration_number=iteration_number,
                candidate_id=loop.current_candidate.candidate_id,
                state=LoopState.REPAIR_VALIDATED,
                analysis_result=bundle.source_id,
                generated_artifacts=patched_project.content_hash(),
                compilation_result=recomp,
                test_result=retest,
                comparison_result=recompare,
                failures=failures,
                repair_attempt=proposal,
                confidence=score2.value,
                decision=f"repair applied: {repair_outcome.value}",
                timestamp=clock(),
            )
        )
        _audit(
            iteration_number=iteration_number,
            event_type=AuditEventType.ITERATION_COMPLETED,
            actor="quality_loop",
            decision=repair_outcome.value,
        )

        new_project_hash = patched_project.content_hash()
        new_diag_sig = recomp.diagnostic_signature()
        new_cmp_sig = _comparison_signature(recompare)
        new_test_sig = _test_signature(retest)
        # "candidate behavior doesn't improve" is operationalized by the four
        # concrete signature checks below (identical diagnostics / identical
        # behavioral differences / identical patch (checked earlier) /
        # unchanged artifact hash) -- a NO_CHANGE *count* alone does not stop
        # the loop as long as the actual failing value is genuinely different
        # each time (e.g. fixing one of several independent failures per
        # iteration), so MAX_ITERATIONS can still be reached honestly.
        no_progress = (
            new_project_hash in seen_project_hashes
            or (recomp.success is False and new_diag_sig in seen_diag_sigs)
            or (recompare is not None and new_cmp_sig in seen_cmp_sigs)
            or (retest is not None and new_test_sig in seen_test_sigs)
        )
        seen_project_hashes.add(new_project_hash)
        seen_diag_sigs.add(new_diag_sig)
        seen_cmp_sigs.add(new_cmp_sig)
        seen_test_sigs.add(new_test_sig)

        if no_progress and cfg.escalate_on_no_progress:
            return _finish(
                final_status=FinalStatus.STOPPED,
                stop_reason=StopReason.NO_PROGRESS,
                human_review_required=False,
                loop_state=LoopState.STOPPED,
                iteration_number=iteration_number,
                reason="repair produced no measurable improvement",
            )

        # accept: version the candidate forward and continue the loop
        new_candidate = next_candidate(
            loop.current_candidate, project=patched_project, test_suite=suite
        )
        loop = loop.with_new_candidate(new_candidate)
        current_project = patched_project
        loop = loop.transition(LoopState.COMPILING)

    return _finish(
        final_status=FinalStatus.STOPPED,
        stop_reason=StopReason.MAX_ITERATIONS_REACHED,
        human_review_required=True,
        loop_state=LoopState.STOPPED,
        iteration_number=cfg.max_iterations - 1,
        reason=f"reached max_iterations={cfg.max_iterations} without PASS",
    )
