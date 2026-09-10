"""Phase 11 — LoopState machine, config, candidate versioning, audit-log wiring."""

from __future__ import annotations

import pytest

from app.quality_loop.audit import AuditEventType, AuditLog
from app.quality_loop.errors import InvalidStateTransitionError
from app.quality_loop.models import (
    CandidateVersion,
    FinalStatus,
    LoopState,
    QualityLoop,
    QualityLoopConfig,
    StopReason,
    build_candidate_id,
    validate_transition,
)


def _candidate(version: int = 1) -> CandidateVersion:
    return CandidateVersion(
        candidate_id=build_candidate_id(
            source_hash="src1",
            architecture_hash="arch1",
            generated_project_hash="proj1",
            test_set_hash="test1",
            version=version,
        ),
        version=version,
        architecture_hash="arch1",
        source_hash="src1",
        generated_project_hash="proj1",
        test_set_hash="test1",
    )


def _loop() -> QualityLoop:
    return QualityLoop(
        loop_id="loop-1",
        modernization_id="mod-1",
        configuration=QualityLoopConfig(),
        current_candidate=_candidate(),
        audit_log=AuditLog(loop_id="loop-1"),
    )


class TestLoopStateMachine:
    def test_valid_forward_path(self):
        for a, b in [
            (LoopState.ANALYZING, LoopState.GENERATING),
            (LoopState.GENERATING, LoopState.COMPILING),
            (LoopState.COMPILING, LoopState.TESTING),
            (LoopState.TESTING, LoopState.COMPARING),
            (LoopState.COMPARING, LoopState.COMPLETED),
        ]:
            validate_transition(a, b)  # must not raise

    def test_repair_path(self):
        for a, b in [
            (LoopState.COMPARING, LoopState.FAILURE_DETECTED),
            (LoopState.FAILURE_DETECTED, LoopState.REPAIR_PROPOSED),
            (LoopState.REPAIR_PROPOSED, LoopState.REPAIR_VALIDATED),
            (LoopState.REPAIR_VALIDATED, LoopState.COMPILING),
        ]:
            validate_transition(a, b)

    def test_illegal_skip_is_rejected(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(LoopState.ANALYZING, LoopState.COMPLETED)

    def test_illegal_backward_jump_is_rejected(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(LoopState.COMPILING, LoopState.ANALYZING)

    def test_terminal_states_have_no_outgoing_transitions(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(LoopState.COMPLETED, LoopState.ANALYZING)
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(LoopState.STOPPED, LoopState.ANALYZING)

    def test_human_review_can_resume_or_terminate(self):
        validate_transition(LoopState.HUMAN_REVIEW, LoopState.ANALYZING)
        validate_transition(LoopState.HUMAN_REVIEW, LoopState.REPAIR_PROPOSED)
        validate_transition(LoopState.HUMAN_REVIEW, LoopState.COMPLETED)
        validate_transition(LoopState.HUMAN_REVIEW, LoopState.STOPPED)

    def test_quality_loop_transition_method_enforces_the_same_rules(self):
        loop = _loop()
        assert loop.state is LoopState.ANALYZING
        loop = loop.transition(LoopState.GENERATING)
        assert loop.state is LoopState.GENERATING
        with pytest.raises(InvalidStateTransitionError):
            loop.transition(LoopState.COMPLETED)


class TestCandidateVersioning:
    def test_candidate_id_is_deterministic(self):
        a = build_candidate_id(
            source_hash="s",
            architecture_hash="a",
            generated_project_hash="g",
            test_set_hash="t",
            version=1,
        )
        b = build_candidate_id(
            source_hash="s",
            architecture_hash="a",
            generated_project_hash="g",
            test_set_hash="t",
            version=1,
        )
        assert a == b

    def test_different_version_gives_different_id(self):
        a = build_candidate_id(
            source_hash="s",
            architecture_hash="a",
            generated_project_hash="g",
            test_set_hash="t",
            version=1,
        )
        b = build_candidate_id(
            source_hash="s",
            architecture_hash="a",
            generated_project_hash="g",
            test_set_hash="t",
            version=2,
        )
        assert a != b

    def test_loop_with_new_candidate_preserves_history_never_overwrites(self):
        loop = _loop()
        c1 = loop.current_candidate
        c2 = _candidate(version=2)
        loop2 = loop.with_new_candidate(c2)
        assert loop2.current_candidate == c2
        assert c1 in loop2.candidate_history
        assert loop.current_candidate == c1  # original loop object untouched


class TestQualityLoopConfig:
    def test_defaults_match_spec_example(self):
        cfg = QualityLoopConfig()
        assert cfg.max_iterations == 3
        assert cfg.repair_confidence_threshold == 0.80
        assert cfg.auto_apply_threshold == 0.90
        assert cfg.human_review_threshold == 0.60

    def test_max_iterations_is_configurable_not_hardcoded(self):
        cfg = QualityLoopConfig(max_iterations=7)
        assert cfg.max_iterations == 7

    def test_thresholds_are_bounded_0_to_1(self):
        with pytest.raises(Exception):
            QualityLoopConfig(human_review_threshold=1.5)


class TestFinishAndAudit:
    def test_finish_sets_final_status_and_never_mutates_in_place(self):
        loop = _loop()
        finished = loop.finish(
            final_status=FinalStatus.PASS, stop_reason=None, human_review_required=False
        )
        assert finished.final_status is FinalStatus.PASS
        assert loop.final_status is None  # original untouched

    def test_finish_stopped_carries_a_reason(self):
        loop = _loop().finish(
            final_status=FinalStatus.STOPPED,
            stop_reason=StopReason.MAX_ITERATIONS_REACHED,
            human_review_required=True,
        )
        assert loop.final_status is FinalStatus.STOPPED
        assert loop.stop_reason is StopReason.MAX_ITERATIONS_REACHED
        assert loop.human_review_required is True

    def test_audit_log_is_serializable_round_trip(self):
        log = AuditLog(loop_id="loop-1")
        log = log.append(
            timestamp="t0",
            iteration_number=0,
            event_type=AuditEventType.ANALYSIS_STARTED,
            actor="quality_loop",
        )
        d = log.to_dict()
        assert d["event_count"] == 1
        assert d["chain_valid"] is True
