"""
Evidence-based "confidence" scoring (Phase 11).

This is a **heuristic**, not a calibrated probability. It is
deliberately never the LLM's own self-reported confidence — the model
must not get to decide its own authority. Instead it is a fixed-weight
sum of *observable* evidence properties of the failure + proposed
context (source mapping present, business rule identified, single
affected artifact, precise diagnostic, localized difference, complete
context), plus one post-hoc factor that only exists after a patch has
actually been mechanically parsed/validated (never from what the model
claims about itself).

    ``CONFIDENCE_MODEL_VERSION`` (see version.py) identifies this
    specific weighting scheme so any change to it is auditable.

Threshold policy (the most conservative reading of the spec's three
named thresholds -- documented explicitly, not left implicit):

    confidence <  human_review_threshold        -> HUMAN_REVIEW, no patch proposed
    confidence <  repair_confidence_threshold    -> HUMAN_REVIEW, patch proposed+validated for a reviewer, not applied
    patch fails validation                       -> REPAIR_REJECTED -> HUMAN_REVIEW
    confidence <  auto_apply_threshold           -> HUMAN_REVIEW, valid patch awaiting human approval
    confidence >= auto_apply_threshold           -> auto-apply

The model can never override this by reporting a higher number itself.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.quality_loop.failure import FailureRecord
from app.quality_loop.models import QualityLoopConfig
from app.quality_loop.version import CONFIDENCE_MODEL_VERSION

__all__ = [
    "ConfidenceAction",
    "ConfidenceFactors",
    "ConfidenceScore",
    "compute_confidence",
    "decide_confidence_action",
]

# fixed weights, sum to 1.0 -- documented, not tunable per-request
_WEIGHTS: dict[str, float] = {
    "has_source_mapping": 0.25,
    "has_business_rule": 0.15,
    "single_affected_artifact": 0.20,
    "diagnostic_precise": 0.20,
    "localized": 0.10,
    "context_complete": 0.10,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9


class ConfidenceFactors(BaseModel):
    """Observable evidence properties -- each True/False, never a claim
    the LLM makes about itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    has_source_mapping: bool
    has_business_rule: bool
    single_affected_artifact: bool
    diagnostic_precise: bool
    localized: bool
    context_complete: bool
    #: only known after the patch has been mechanically validated
    #: (#128's ``validate_patch``) -- absent (None) before that point.
    patch_structurally_valid: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ConfidenceScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    confidence_model_version: str = CONFIDENCE_MODEL_VERSION
    value: float = Field(ge=0.0, le=1.0)
    label: str = "heuristic confidence (not calibrated; not a probability)"
    factors: ConfidenceFactors
    breakdown: dict[str, float] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def compute_confidence(factors: ConfidenceFactors) -> ConfidenceScore:
    breakdown: dict[str, float] = {}
    total = 0.0
    for name, weight in _WEIGHTS.items():
        on = bool(getattr(factors, name))
        contribution = weight if on else 0.0
        breakdown[name] = contribution
        total += contribution

    # a structurally invalid patch caps confidence outright -- mechanical
    # fact, not something the model can talk its way around.
    if factors.patch_structurally_valid is False:
        total = min(total, 0.10)
        breakdown["patch_structurally_valid_penalty"] = -1.0

    total = max(0.0, min(1.0, total))
    return ConfidenceScore(value=round(total, 4), factors=factors, breakdown=breakdown)


class ConfidenceAction(str, Enum):
    NO_PATCH_PROPOSE = (
        "NO_PATCH_PROPOSE"  # too little evidence to even try -> HUMAN_REVIEW
    )
    PROPOSE_FOR_REVIEW = "PROPOSE_FOR_REVIEW"  # propose+validate, human must approve
    AUTO_APPLY = "AUTO_APPLY"  # validated patch may be applied without waiting


def decide_confidence_action(
    score: float, config: QualityLoopConfig
) -> tuple[ConfidenceAction, str]:
    """The model never picks this -- purely a function of the (evidence-based)
    score against the operator-configured, explicitly-labeled-heuristic
    thresholds."""
    if score < config.human_review_threshold:
        return (
            ConfidenceAction.NO_PATCH_PROPOSE,
            f"confidence {score:.2f} < human_review_threshold "
            f"{config.human_review_threshold:.2f}",
        )
    if score < config.repair_confidence_threshold:
        return (
            ConfidenceAction.PROPOSE_FOR_REVIEW,
            f"confidence {score:.2f} < repair_confidence_threshold "
            f"{config.repair_confidence_threshold:.2f} -> human approval required",
        )
    if score < config.auto_apply_threshold:
        return (
            ConfidenceAction.PROPOSE_FOR_REVIEW,
            f"confidence {score:.2f} < auto_apply_threshold "
            f"{config.auto_apply_threshold:.2f} -> valid patch awaits human approval",
        )
    return (
        ConfidenceAction.AUTO_APPLY,
        f"confidence {score:.2f} >= auto_apply_threshold "
        f"{config.auto_apply_threshold:.2f}",
    )


def factors_from_failure_group(
    failures: tuple[FailureRecord, ...],
    *,
    context_complete: bool,
) -> ConfidenceFactors:
    """Derive the observable evidence factors for one repair-candidate
    failure group (already grouped by :func:`app.quality_loop.failure.group_failures`).
    """
    artifacts = {f.affected_artifact for f in failures if f.affected_artifact}
    return ConfidenceFactors(
        has_source_mapping=all(f.source_mapping is not None for f in failures),
        has_business_rule=any(f.business_rule_ids for f in failures),
        single_affected_artifact=len(artifacts) <= 1,
        diagnostic_precise=all(
            f.source_mapping is not None and f.source_mapping.line_start is not None
            for f in failures
        ),
        localized=len(failures) == 1,
        context_complete=context_complete,
    )
