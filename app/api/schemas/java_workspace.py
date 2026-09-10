"""
Java Workspace API Schema.

Aggregates the real #126 generated Java project, #127 compilation
result, and #131 behavioral validation status (reused via the same
PipelineCache-backed pipeline as PR #122 -- no second pipeline cache,
no re-implemented analysis) with the real, deterministic Phase 11
candidate identity (``first_candidate()`` -- pure content hashing, no
LLM).

Quality-loop EXECUTION state (iterations, repair history, audit trail,
human review) is only ever non-empty when
``app.quality_loop.loop.run_quality_loop()`` has actually been run for
this analysis. That function requires a configured ``LLMProvider``
(a required, non-Optional parameter), and
``app.api.dependencies.ai.get_llm_provider()`` returns ``None`` in this
environment -- so those fields are honestly empty / NOT_AVAILABLE here,
never fabricated, never inferred from the fact that a candidate exists.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.validation import StageStatus
from app.behavioral.comparison.models import Phase10Report
from app.java_modernization.compilation.models import CompilationResult
from app.java_modernization.generation.models import GeneratedProject
from app.quality_loop.audit import AuditEvent
from app.quality_loop.models import (
    CandidateVersion,
    FinalStatus,
    QualityIteration,
    StopReason,
)
from app.quality_loop.review import HumanReviewCheckpoint

__all__ = ["JavaWorkspaceResponse"]


class JavaWorkspaceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str
    filename: str

    # -- Generation / Compilation / Behavioral: the SAME pipeline results
    # PR #122's /java and /validation endpoints already expose, reused
    # here rather than recomputed a second time.
    generation_available: bool
    generation_reason: str | None = None
    project: GeneratedProject | None = None
    compilation: CompilationResult | None = None
    compilation_status: StageStatus
    behavioral_status: StageStatus
    behavioral: Phase10Report | None = None

    # -- Candidate identity: real, deterministic (Phase 11's own
    # first_candidate() content-hash function) -- no LLM, no repair.
    current_candidate: CandidateVersion | None = Field(
        default=None,
        description=(
            "The candidate identity for the currently generated project, "
            "computed by Phase 11's first_candidate() (pure content "
            "hashing). This exists independently of whether any repair "
            "loop has ever run."
        ),
    )
    candidate_lineage: list[CandidateVersion] = Field(
        default_factory=list,
        description=(
            "current_candidate plus every prior version, oldest first. "
            "With no repair loop ever run, this is exactly "
            "[current_candidate] (version 1) -- never fabricated history."
        ),
    )

    # -- Quality-loop EXECUTION state: only non-empty if run_quality_loop()
    # actually ran. It cannot run in this environment (no LLM provider),
    # so quality_loop_available is always False here -- see quality_loop_reason.
    quality_loop_available: bool = False
    quality_loop_reason: str = ""
    loop_state: str | None = None
    final_status: FinalStatus | None = None
    stop_reason: StopReason | None = None
    iteration_count: int = 0
    repair_count: int = 0
    iterations: list[QualityIteration] = Field(default_factory=list)
    human_review_required: bool = False
    human_review_checkpoints: list[HumanReviewCheckpoint] = Field(default_factory=list)
    audit_trail: list[AuditEvent] = Field(default_factory=list)
