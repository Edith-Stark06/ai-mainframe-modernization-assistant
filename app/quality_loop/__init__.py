"""
Phase 11 — AI Self-Repair & Quality Loop.

Orchestrates the deterministic Analyze -> Generate -> Compile -> Test ->
Compare pipeline (#125-#131) through a bounded, auditable repair loop.
The pipeline stays authoritative; AI only proposes a targeted repair
after deterministic evidence identifies an eligible failure, and every
repair is mechanically validated, recompiled, retested and recompared
before it can be accepted. See ``docs/PHASE11.md`` for the full design.
"""

from __future__ import annotations

from app.quality_loop.audit import AuditEvent, AuditEventType, AuditLog
from app.quality_loop.candidate import first_candidate, next_candidate
from app.quality_loop.confidence import (
    ConfidenceAction,
    ConfidenceFactors,
    ConfidenceScore,
    compute_confidence,
    decide_confidence_action,
)
from app.quality_loop.eligibility import repair_eligibility
from app.quality_loop.errors import (
    InvalidStateTransitionError,
    QualityLoopError,
    ReviewError,
)
from app.quality_loop.failure import (
    FailureCategory,
    FailureRecord,
    FailureSeverity,
    classify_failures,
)
from app.quality_loop.loop import run_quality_loop
from app.quality_loop.models import (
    CandidateVersion,
    FinalStatus,
    LoopState,
    QualityIteration,
    QualityLoop,
    QualityLoopConfig,
    RepairOutcome,
    RepairProposalRecord,
    StopReason,
)
from app.quality_loop.repair_engine import QualityRepairEngine
from app.quality_loop.review import (
    HumanReviewBoard,
    HumanReviewCheckpoint,
    ReviewDecision,
    ReviewRecord,
    ReviewStatus,
)
from app.quality_loop.version import (
    AUDIT_SCHEMA_VERSION,
    CONFIDENCE_MODEL_VERSION,
    QUALITY_LOOP_VERSION,
)

__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditLog",
    "first_candidate",
    "next_candidate",
    "ConfidenceAction",
    "ConfidenceFactors",
    "ConfidenceScore",
    "compute_confidence",
    "decide_confidence_action",
    "repair_eligibility",
    "InvalidStateTransitionError",
    "QualityLoopError",
    "ReviewError",
    "FailureCategory",
    "FailureRecord",
    "FailureSeverity",
    "classify_failures",
    "run_quality_loop",
    "CandidateVersion",
    "FinalStatus",
    "LoopState",
    "QualityIteration",
    "QualityLoop",
    "QualityLoopConfig",
    "RepairOutcome",
    "RepairProposalRecord",
    "StopReason",
    "QualityRepairEngine",
    "HumanReviewBoard",
    "HumanReviewCheckpoint",
    "ReviewDecision",
    "ReviewRecord",
    "ReviewStatus",
    "AUDIT_SCHEMA_VERSION",
    "CONFIDENCE_MODEL_VERSION",
    "QUALITY_LOOP_VERSION",
]
