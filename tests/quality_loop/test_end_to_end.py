"""
Phase 11 end-to-end tests (deterministic: no live LLM, no COBOL runtime).

    COBOL fixture -> Analyze/Generate (reused, Phase 9) -> quality loop
    (Compile -> Test -> Compare -> Repair) -> PASS / FAIL / INCONCLUSIVE /
    HUMAN_REVIEW / STOPPED

Real Java (javac/java) is always used. COBOL is stood in for with a
deterministic :class:`ScriptedExecutor`, exactly as Phase 10 does,
"to prove the comparison logic independently of external runtime
availability" — never a fabricated real-COBOL result.
"""

from __future__ import annotations

import json
import re

import pytest

from app.ai.providers.base import LLMProvider
from app.ai.providers.models import LLMRequest, LLMResponse
from app.behavioral import ExecutionResult, ScriptedExecutor
from app.java_modernization.compilation import JavaCompiler, javac_available
from app.quality_loop.models import (
    FinalStatus,
    LoopState,
    QualityLoopConfig,
    RepairOutcome,
    StopReason,
)
from app.quality_loop.loop import run_quality_loop
from app.quality_loop.audit import AuditEventType

pytestmark = pytest.mark.skipif(not javac_available(), reason="javac not on PATH")


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------


def _break(project, old: str, new: str):
    main = f"src/{project.main_class}.java"
    return project.model_copy(
        update={"files": {**project.files, main: project.files[main].replace(old, new)}}
    )


def _scripted_if_else_cobol_ground_truth() -> ScriptedExecutor:
    """A deterministic stand-in for COBOL that always reports the CORRECT
    answer for AGE, independent of whatever the (possibly broken) generated
    Java currently does — exactly as tests/behavioral does."""

    def script(inputs: dict[str, str]) -> ExecutionResult:
        age = int(inputs.get("AGE", "0"))
        correct = "ADULT" if age > 18 else "MINOR"
        return ExecutionResult(
            executed=True,
            success=True,
            executor_kind="scripted",
            outputs={"stdout[0]": correct},
        )

    return ScriptedExecutor({"IFELSE": script})


def _max_line_number(prompt: str) -> int:
    nums = []
    for ln in prompt.splitlines():
        m = re.match(r"\s*(\d+)\|", ln)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 20


def _full_source(main_class: str, body: str) -> str:
    return (
        f"public class {main_class} {{\n\n"
        f"    private int age;\n\n"
        f"    public static void main(String[] args) {{\n"
        f"        new {main_class}().run();\n"
        f"    }}\n\n"
        f"    public void run() {{\n\n"
        f"{body}"
        f"        return;\n\n"
        f"    }}\n\n"
        f"}}"
    )


_CORRECT_BODY = (
    "        if (age > 18) {\n"
    '            System.out.println("ADULT");\n'
    "        } else {\n"
    '            System.out.println("MINOR");\n'
    "        }\n"
)


def _patch_response(
    path: str, start_line: int, end_line: int, replacement: str, note: str
) -> str:
    return json.dumps(
        {
            "files": [
                {
                    "path": path,
                    "changes": [
                        {
                            "start_line": start_line,
                            "end_line": end_line,
                            "replacement": replacement,
                        }
                    ],
                }
            ],
            "explanation": note,
            "source_basis": ["E1"],
        }
    )


class _NeverCalledProvider(LLMProvider):
    """Proves the loop never invokes the model when no repair is needed
    or none is eligible."""

    def generate(self, request: LLMRequest) -> LLMResponse:  # noqa: ANN001
        raise AssertionError("the AI must not be invoked here")


class _SemicolonFixer(LLMProvider):
    """Restores a missing semicolon after `System.out.println("ADULT")`."""

    def __init__(self, main_class: str) -> None:
        self.main_class = main_class
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        line = None
        for ln in request.prompt.splitlines():
            m = re.match(r'\s*(\d+)\|\s+System\.out\.println\("ADULT"\)\s*$', ln)
            if m:
                line = int(m.group(1))
        assert line is not None, "broken line was not found in the repair context"
        return LLMResponse(
            text=_patch_response(
                f"src/{self.main_class}.java",
                line,
                line,
                '            System.out.println("ADULT");',
                "restore missing semicolon",
            ),
            model="semicolon-fixer",
        )


class _BehavioralFixer(LLMProvider):
    """Restores the correct `age > 18` condition (full-file replacement --
    behavioral evidence carries no precise Java line, unlike a compiler
    diagnostic, so the whole affected file is replaced)."""

    def __init__(self, main_class: str) -> None:
        self.main_class = main_class
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        n = _max_line_number(request.prompt)
        return LLMResponse(
            text=_patch_response(
                f"src/{self.main_class}.java",
                1,
                n,
                _full_source(self.main_class, _CORRECT_BODY),
                "restore the age > 18 boundary condition",
            ),
            model="behavioral-fixer",
        )


class _RegressionInducer(LLMProvider):
    """ "Fixes" the one failing case by widening the condition so far it
    breaks two other, previously-passing cases."""

    def __init__(self, main_class: str) -> None:
        self.main_class = main_class
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        n = _max_line_number(request.prompt)
        body = (
            "        if (age > 0) {\n"
            '            System.out.println("ADULT");\n'
            "        } else {\n"
            '            System.out.println("MINOR");\n'
            "        }\n"
        )
        return LLMResponse(
            text=_patch_response(
                f"src/{self.main_class}.java",
                1,
                n,
                _full_source(self.main_class, body),
                "widen the eligibility condition",
            ),
            model="regression-inducer",
        )


class _VaryingWrongFixer(LLMProvider):
    """Proposes a genuinely different (but still wrong) fix every call --
    never converges, never repeats -- to exercise the max_iterations cap."""

    def __init__(self, main_class: str) -> None:
        self.main_class = main_class
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        n = _max_line_number(request.prompt)
        body = (
            "        if (age == 19) {\n"
            f'            System.out.println("WRONG-{self.calls}");\n'
            "        } else if (age > 18) {\n"
            '            System.out.println("ADULT");\n'
            "        } else {\n"
            '            System.out.println("MINOR");\n'
            "        }\n"
        )
        return LLMResponse(
            text=_patch_response(
                f"src/{self.main_class}.java",
                1,
                n,
                _full_source(self.main_class, body),
                f"attempt {self.calls}",
            ),
            model="varying-wrong-fixer",
        )


class _IdenticalWrongFixer(LLMProvider):
    """Proposes the EXACT same (wrong) fix every call -- must be caught as
    a duplicate patch and stop the loop early."""

    def __init__(self, main_class: str) -> None:
        self.main_class = main_class
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        n = _max_line_number(request.prompt)
        body = (
            "        if (age == 19) {\n"
            '            System.out.println("STILL-WRONG");\n'
            "        } else if (age > 18) {\n"
            '            System.out.println("ADULT");\n'
            "        } else {\n"
            '            System.out.println("MINOR");\n'
            "        }\n"
        )
        return LLMResponse(
            text=_patch_response(
                f"src/{self.main_class}.java",
                1,
                n,
                _full_source(self.main_class, body),
                "same fix every time",
            ),
            model="stuck-fixer",
        )


# --------------------------------------------------------------------------
# TEST 1 — successful loop, PASS, no repair
# --------------------------------------------------------------------------


def test_1_successful_loop_reaches_pass_without_any_repair(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        if_else_project,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=_NeverCalledProvider(),
        modernization_id="MOD-IFELSE-1",
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.PASS
    assert loop.state is LoopState.COMPLETED
    assert loop.human_review_required is False
    assert len(loop.iterations) == 1
    assert board.checkpoints == ()
    assert loop.current_candidate.version == 1
    assert not any(
        e.event_type is AuditEventType.FAILURE_DETECTED for e in loop.audit_log.events
    )


# --------------------------------------------------------------------------
# TEST 2 — compilation error repair -> PASS, full audit history
# --------------------------------------------------------------------------


def test_2_compilation_repair_reaches_pass_with_full_audit_history(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    broken = _break(
        if_else_project, 'System.out.println("ADULT");', 'System.out.println("ADULT")'
    )
    fixer = _SemicolonFixer(if_else_project.main_class)
    # this codebase's compile-diagnostic -> business-rule mapping is coarse
    # for a plain call-site syntax fix (no business rule attaches to a
    # missing semicolon), so realistic evidence here tops out ~0.65 --
    # auto_apply_threshold is lowered for this scenario to demonstrate the
    # full propose -> validate -> apply -> recompile -> retest -> recompare
    # -> PASS mechanics; the confidence *gate* itself is covered by TEST 5.
    cfg = QualityLoopConfig(
        human_review_threshold=0.3,
        repair_confidence_threshold=0.4,
        auto_apply_threshold=0.5,
    )
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        broken,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=fixer,
        modernization_id="MOD-IFELSE-2",
        config=cfg,
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.PASS
    assert loop.state is LoopState.COMPLETED
    assert fixer.calls == 1
    assert loop.current_candidate.version == 2  # one accepted repair -> new candidate
    assert board.checkpoints == ()

    types = [e.event_type for e in loop.audit_log.events]
    for required in (
        AuditEventType.COMPILATION_STARTED,
        AuditEventType.COMPILATION_COMPLETED,
        AuditEventType.FAILURE_DETECTED,
        AuditEventType.REPAIR_REQUESTED,
        AuditEventType.REPAIR_PROPOSED,
        AuditEventType.REPAIR_APPLIED,
        AuditEventType.ITERATION_COMPLETED,
        AuditEventType.LOOP_COMPLETED,
    ):
        assert required in types
    assert types.count(AuditEventType.COMPILATION_STARTED) == 2  # broken, then fixed
    assert loop.audit_log.verify_chain() is True


# --------------------------------------------------------------------------
# TEST 3 — behavioral repair -> PASS, deterministic fake COBOL + real Java
# --------------------------------------------------------------------------


def test_3_behavioral_repair_reaches_pass(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    # only AGE == 19 misbehaves (condition widened to `age > 19`); AGE 17/18
    # still behave correctly, so this is a single, localized failure.
    broken = _break(if_else_project, "age > 18", "age > 19")
    fixer = _BehavioralFixer(if_else_project.main_class)
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        broken,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=fixer,
        modernization_id="MOD-IFELSE-3",
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.PASS
    assert loop.state is LoopState.COMPLETED
    assert fixer.calls == 1
    assert board.checkpoints == ()
    repaired_iteration = next(
        it for it in loop.iterations if it.repair_attempt is not None
    )
    assert repaired_iteration.repair_attempt.applied is True
    assert repaired_iteration.repair_attempt.outcome is RepairOutcome.PASS


# --------------------------------------------------------------------------
# TEST 4 — repair causes a regression -> REGRESSION, candidate NOT accepted
# --------------------------------------------------------------------------


def test_4_repair_regression_is_rejected_not_accepted(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    broken = _break(if_else_project, "age > 18", "age > 19")  # only AGE==19 fails
    inducer = _RegressionInducer(if_else_project.main_class)
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        broken,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=inducer,
        modernization_id="MOD-IFELSE-4",
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.HUMAN_REVIEW
    assert loop.stop_reason is StopReason.REPAIR_REJECTED
    assert loop.human_review_required is True
    assert loop.current_candidate.version == 1  # never advanced past the original
    assert len(board.pending()) == 1
    assert "regress" in board.pending()[0].reason.lower()

    repaired_iteration = next(
        it for it in loop.iterations if it.repair_attempt is not None
    )
    assert repaired_iteration.repair_attempt.outcome is RepairOutcome.REGRESSION


# --------------------------------------------------------------------------
# TEST 5 — low confidence -> HUMAN_REVIEW, no auto-apply
# --------------------------------------------------------------------------


def test_5_low_confidence_requires_human_review_no_auto_apply(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    broken = _break(
        if_else_project, 'System.out.println("ADULT");', 'System.out.println("ADULT")'
    )
    fixer = _SemicolonFixer(if_else_project.main_class)
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        broken,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=fixer,
        modernization_id="MOD-IFELSE-5",  # default thresholds
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.HUMAN_REVIEW
    assert loop.human_review_required is True
    assert len(board.pending()) == 1
    # no auto-apply: the candidate was never advanced/replaced
    assert loop.current_candidate.version == 1
    assert not any(
        e.event_type is AuditEventType.REPAIR_APPLIED for e in loop.audit_log.events
    )


# --------------------------------------------------------------------------
# TEST 6 — unsupported behavior -> INCONCLUSIVE, no speculative repair
# --------------------------------------------------------------------------


def test_6_unsupported_behavior_is_inconclusive_never_speculative(
    elig_bundle, elig_architecture, elig_project, tmp_path
):
    loop, board = run_quality_loop(
        elig_bundle,
        elig_architecture,
        elig_project,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=_NeverCalledProvider(),
        modernization_id="MOD-ELIG-6",
        # no cobol_executor override: real (unavailable) CobolExecutor is used
    )
    assert loop.final_status is FinalStatus.INCONCLUSIVE
    assert loop.stop_reason is StopReason.NO_ELIGIBLE_REPAIR
    assert loop.current_candidate.version == 1
    assert not any(
        e.event_type is AuditEventType.REPAIR_REQUESTED for e in loop.audit_log.events
    )


# --------------------------------------------------------------------------
# TEST 7 — maximum iterations reached, exactly 3, then STOPPED
# --------------------------------------------------------------------------


def test_7_stops_at_exactly_max_iterations(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    broken = _break(if_else_project, "age > 18", "age > 19")
    fixer = _VaryingWrongFixer(if_else_project.main_class)
    cfg = QualityLoopConfig(max_iterations=3)
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        broken,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=fixer,
        modernization_id="MOD-IFELSE-7",
        config=cfg,
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.STOPPED
    assert loop.stop_reason is StopReason.MAX_ITERATIONS_REACHED
    assert len(loop.iterations) == 3
    assert fixer.calls == 3  # no 4th repair attempt
    assert (
        loop.current_candidate.version == 4
    )  # v1 + 3 accepted (non-regressing) repairs


# --------------------------------------------------------------------------
# TEST 8 — no progress -> early STOPPED, well before max_iterations
# --------------------------------------------------------------------------


def test_8_no_progress_stops_early(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    broken = _break(if_else_project, "age > 18", "age > 19")
    fixer = _IdenticalWrongFixer(if_else_project.main_class)
    cfg = QualityLoopConfig(max_iterations=3)
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        broken,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=fixer,
        modernization_id="MOD-IFELSE-8",
        config=cfg,
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.STOPPED
    assert loop.stop_reason is StopReason.NO_PROGRESS
    assert len(loop.iterations) < cfg.max_iterations
    assert fixer.calls == 2  # accepted once, then caught as a duplicate patch


# --------------------------------------------------------------------------
# TEST 9 — the complete process is reconstructable SOLELY from the audit log
# --------------------------------------------------------------------------


def test_9_audit_log_alone_reconstructs_the_full_failure_to_result_story(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    broken = _break(
        if_else_project, 'System.out.println("ADULT");', 'System.out.println("ADULT")'
    )
    fixer = _SemicolonFixer(if_else_project.main_class)
    cfg = QualityLoopConfig(
        human_review_threshold=0.3,
        repair_confidence_threshold=0.4,
        auto_apply_threshold=0.5,
    )
    loop, board = run_quality_loop(
        if_else_bundle,
        if_else_architecture,
        broken,
        workspace_root=tmp_path,
        compiler=JavaCompiler(tmp_path),
        provider=fixer,
        modernization_id="MOD-IFELSE-9",
        config=cfg,
        cobol_executor=_scripted_if_else_cobol_ground_truth(),
    )
    assert loop.final_status is FinalStatus.PASS
    assert loop.audit_log.verify_chain() is True

    events = loop.audit_log.events
    by_type = {}
    for e in events:
        by_type.setdefault(e.event_type, []).append(e)

    # what failed, and why
    failure_evt = by_type[AuditEventType.FAILURE_DETECTED][0]
    assert failure_evt.decision == "COMPILATION_ERROR"
    assert failure_evt.output_refs  # failure_id(s) referenced

    # why repair was attempted + what evidence backed it
    requested_evt = by_type[AuditEventType.REPAIR_REQUESTED][0]
    assert requested_evt.input_refs  # grounded context refs

    # what the AI proposed
    proposed_evt = by_type[AuditEventType.REPAIR_PROPOSED][0]
    assert proposed_evt.actor == "ai_provider"
    assert proposed_evt.output_refs  # patch signature
    assert proposed_evt.reason  # explanation

    # what exactly changed
    applied_evt = by_type[AuditEventType.REPAIR_APPLIED][0]
    assert applied_evt.output_refs  # new project hash

    # compile/test/behavior improved: two full compile passes, second succeeds
    comp_events = by_type[AuditEventType.COMPILATION_COMPLETED]
    assert len(comp_events) == 2
    assert comp_events[0].decision == "failed"
    assert comp_events[1].decision == "success"

    # no regression flagged anywhere
    assert AuditEventType.REPAIR_REJECTED not in by_type

    # why the loop stopped/completed, and with what final decision
    completed_evt = by_type[AuditEventType.LOOP_COMPLETED][0]
    assert completed_evt.decision == "PASS"

    # every event references its loop and is strictly ordered
    assert all(e.loop_id == loop.loop_id for e in events)
    assert [e.sequence for e in events] == sorted(e.sequence for e in events)
