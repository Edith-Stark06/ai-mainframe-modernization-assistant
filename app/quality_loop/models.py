"""
Core state/data model for the Phase 11 quality loop.

The deterministic pipeline (Analyze -> Generate -> Compile -> Test ->
Compare) stays authoritative; this module only adds the bookkeeping
needed to drive it through a bounded, auditable repair loop:

    * :class:`LoopState` — an explicit state machine; illegal
      transitions raise :class:`~app.quality_loop.errors.InvalidStateTransitionError`.
    * :class:`CandidateVersion` — immutable identity for one generated
      candidate; a repair always produces a *new* version, never an
      overwrite.
    * :class:`QualityIteration` — one full pass through the pipeline;
      iterations are appended, never replaced.
    * :class:`QualityLoop` — the aggregate root tying configuration,
      current candidate, iteration history and the audit log together.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.behavioral.comparison.models import Phase10Report
from app.behavioral.javatests.models import JavaTestSuiteResult
from app.java_modernization.compilation.models import CompilationResult
from app.quality_loop.audit import AuditLog
from app.quality_loop.errors import InvalidStateTransitionError
from app.quality_loop.failure import FailureRecord
from app.quality_loop.version import QUALITY_LOOP_VERSION

__all__ = [
    "LoopState",
    "FinalStatus",
    "StopReason",
    "RepairOutcome",
    "QualityLoopConfig",
    "CandidateVersion",
    "RepairProposalRecord",
    "QualityIteration",
    "QualityLoop",
]


class LoopState(str, Enum):
    ANALYZING = "ANALYZING"
    GENERATING = "GENERATING"
    COMPILING = "COMPILING"
    TESTING = "TESTING"
    COMPARING = "COMPARING"
    FAILURE_DETECTED = "FAILURE_DETECTED"
    REPAIR_PROPOSED = "REPAIR_PROPOSED"
    REPAIR_VALIDATED = "REPAIR_VALIDATED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"


#: documented, closed set of allowed transitions -- the only place
#: control flow is permitted to move the loop from one state to another.
_VALID_TRANSITIONS: dict[LoopState, frozenset[LoopState]] = {
    LoopState.ANALYZING: frozenset({LoopState.GENERATING, LoopState.STOPPED}),
    LoopState.GENERATING: frozenset({LoopState.COMPILING, LoopState.STOPPED}),
    LoopState.COMPILING: frozenset(
        {LoopState.TESTING, LoopState.FAILURE_DETECTED, LoopState.STOPPED}
    ),
    LoopState.TESTING: frozenset(
        {LoopState.COMPARING, LoopState.FAILURE_DETECTED, LoopState.STOPPED}
    ),
    LoopState.COMPARING: frozenset(
        {
            LoopState.COMPLETED,
            LoopState.FAILURE_DETECTED,
            LoopState.HUMAN_REVIEW,
            LoopState.STOPPED,
        }
    ),
    LoopState.FAILURE_DETECTED: frozenset(
        {LoopState.REPAIR_PROPOSED, LoopState.HUMAN_REVIEW, LoopState.STOPPED}
    ),
    LoopState.REPAIR_PROPOSED: frozenset(
        {LoopState.REPAIR_VALIDATED, LoopState.HUMAN_REVIEW, LoopState.STOPPED}
    ),
    LoopState.REPAIR_VALIDATED: frozenset(
        {LoopState.COMPILING, LoopState.HUMAN_REVIEW, LoopState.STOPPED}
    ),
    LoopState.HUMAN_REVIEW: frozenset(
        {
            LoopState.ANALYZING,
            LoopState.REPAIR_PROPOSED,
            LoopState.COMPLETED,
            LoopState.STOPPED,
        }
    ),
    LoopState.COMPLETED: frozenset(),
    LoopState.STOPPED: frozenset(),
}


def validate_transition(current: LoopState, target: LoopState) -> None:
    if target not in _VALID_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"illegal quality-loop transition: {current.value} -> {target.value}"
        )


class FinalStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    STOPPED = "STOPPED"


class StopReason(str, Enum):
    MAX_ITERATIONS_REACHED = "MAX_ITERATIONS_REACHED"
    NO_PROGRESS = "NO_PROGRESS"
    TIMEOUT = "TIMEOUT"
    REPAIR_REJECTED = "REPAIR_REJECTED"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    NO_ELIGIBLE_REPAIR = "NO_ELIGIBLE_REPAIR"
    REPAIR_BUDGET_EXHAUSTED = "REPAIR_BUDGET_EXHAUSTED"
    HUMAN_STOP = "HUMAN_STOP"


class RepairOutcome(str, Enum):
    PASS = "PASS"
    PARTIAL_IMPROVEMENT = "PARTIAL_IMPROVEMENT"
    NO_CHANGE = "NO_CHANGE"
    REGRESSION = "REGRESSION"


class QualityLoopConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_iterations: int = Field(default=3, ge=1)
    max_repairs_per_iteration: int = Field(default=1, ge=1)
    max_total_repairs: int = Field(default=3, ge=1)
    max_runtime_s: float | None = Field(default=None, gt=0)

    #: below this -> HUMAN_REVIEW without even proposing a patch
    human_review_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    #: below this (but >= human_review_threshold) -> patch may be proposed
    #: and validated, but requires human approval before it is applied
    repair_confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    #: at/above this -> a *validated* patch may be auto-applied
    auto_apply_threshold: float = Field(default=0.90, ge=0.0, le=1.0)

    escalate_on_no_progress: bool = True


class CandidateVersion(BaseModel):
    """Immutable identity for one generated candidate.

    A repair never overwrites a candidate -- it produces a new version
    (``candidate-v1`` -> ``candidate-v2`` -> ...), chained via
    ``parent_candidate_id``, so prior evidence is never lost.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    version: int = Field(ge=1)
    architecture_hash: str
    source_hash: str
    generated_project_hash: str
    test_set_hash: str
    parent_candidate_id: str | None = None
    created_from_repair: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_candidate_id(
    *,
    source_hash: str,
    architecture_hash: str,
    generated_project_hash: str,
    test_set_hash: str,
    version: int,
) -> str:
    key = "\x1f".join(
        [
            source_hash,
            architecture_hash,
            generated_project_hash,
            test_set_hash,
            str(version),
        ]
    )
    return f"candidate-v{version}-{hashlib.sha256(key.encode()).hexdigest()[:12]}"


class RepairProposalRecord(BaseModel):
    """What the AI proposed for one failure group, and what happened to it.

    Deliberately decoupled from #128's own ``RepairAttempt`` (which is
    scoped to :class:`~app.java_modernization.repair.loop.SelfRepairLoop`'s
    internal bounded loop) -- Phase 11 drives a single propose/validate/
    apply attempt per outer iteration and records the *outcome* here,
    reusing #128's patch models/functions to do the actual parsing,
    validation and application.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_failure_ids: tuple[str, ...]
    patch_signature: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: str
    eligible: bool
    eligibility_reason: str
    validated: bool = False
    rejected_reason: str | None = None
    applied: bool = False
    requires_human_review: bool = False
    outcome: RepairOutcome | None = None
    before_metrics: dict[str, int] = Field(default_factory=dict)
    after_metrics: dict[str, int] = Field(default_factory=dict)
    explanation: str = ""
    source_basis: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class QualityIteration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    iteration_number: int = Field(ge=0)
    candidate_id: str
    state: LoopState
    analysis_result: (
        str  # reference: bundle.source_id (analysis itself is reused, not re-modeled)
    )
    generated_artifacts: str  # reference: generated_project_hash
    compilation_result: CompilationResult | None = None
    test_result: JavaTestSuiteResult | None = None
    comparison_result: Phase10Report | None = None
    failures: tuple[FailureRecord, ...] = ()
    repair_attempt: RepairProposalRecord | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    decision: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class QualityLoop(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    loop_id: str
    modernization_id: str
    quality_loop_version: str = QUALITY_LOOP_VERSION
    configuration: QualityLoopConfig
    current_candidate: CandidateVersion
    candidate_history: tuple[CandidateVersion, ...] = ()
    state: LoopState = LoopState.ANALYZING
    iterations: tuple[QualityIteration, ...] = ()
    final_status: FinalStatus | None = None
    stop_reason: StopReason | None = None
    human_review_required: bool = False
    audit_log: AuditLog

    def transition(self, target: LoopState) -> QualityLoop:
        validate_transition(self.state, target)
        return self.model_copy(update={"state": target})

    def with_new_candidate(self, candidate: CandidateVersion) -> QualityLoop:
        return self.model_copy(
            update={
                "current_candidate": candidate,
                "candidate_history": (*self.candidate_history, self.current_candidate),
            }
        )

    def record_iteration(self, iteration: QualityIteration) -> QualityLoop:
        return self.model_copy(update={"iterations": (*self.iterations, iteration)})

    def finish(
        self,
        *,
        final_status: FinalStatus,
        stop_reason: StopReason | None = None,
        human_review_required: bool = False,
    ) -> QualityLoop:
        return self.model_copy(
            update={
                "final_status": final_status,
                "stop_reason": stop_reason,
                "human_review_required": human_review_required,
            }
        )

    def with_audit_log(self, audit_log: AuditLog) -> QualityLoop:
        return self.model_copy(update={"audit_log": audit_log})

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "modernization_id": self.modernization_id,
            "quality_loop_version": self.quality_loop_version,
            "configuration": self.configuration.model_dump(mode="json"),
            "current_candidate": self.current_candidate.to_dict(),
            "candidate_history": [c.to_dict() for c in self.candidate_history],
            "state": self.state.value,
            "iterations": [it.to_dict() for it in self.iterations],
            "final_status": self.final_status.value if self.final_status else None,
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "human_review_required": self.human_review_required,
            "audit_log": self.audit_log.to_dict(),
        }
