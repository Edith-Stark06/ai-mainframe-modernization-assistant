"""
Human review checkpoints (Phase 11).

This is the real boundary the task requires: the AI proposes a repair,
the deterministic pipeline validates it, and — whenever a review
trigger fires — a *human* decides what happens next through
:meth:`HumanReviewBoard.review`. The model can never call this API on
its own behalf; nothing in this package invokes it except in response
to an external decision.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.quality_loop.errors import ReviewError

__all__ = [
    "ReviewStatus",
    "ReviewDecision",
    "HumanReviewCheckpoint",
    "ReviewRecord",
    "HumanReviewBoard",
]


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_NEW_REPAIR = "REQUEST_NEW_REPAIR"
    STOP = "STOP"


_DECISION_TO_STATUS: dict[ReviewDecision, ReviewStatus] = {
    ReviewDecision.APPROVE: ReviewStatus.APPROVED,
    ReviewDecision.REJECT: ReviewStatus.REJECTED,
    ReviewDecision.REQUEST_NEW_REPAIR: ReviewStatus.REJECTED,
    ReviewDecision.STOP: ReviewStatus.REJECTED,
}


class HumanReviewCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_id: str
    loop_id: str
    iteration_number: int = Field(ge=0)
    reason: str
    evidence: tuple[str, ...] = ()
    proposed_action: str = ""
    status: ReviewStatus = ReviewStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ReviewRecord(BaseModel):
    """Never silently applied -- every human decision is stored, in full."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_id: str
    candidate_id: str
    iteration_number: int = Field(ge=0)
    decision: ReviewDecision
    reviewer: str
    comment: str = ""
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class HumanReviewBoard(BaseModel):
    """In-memory, programmatic checkpoint store. No fake UI -- the
    ``review()`` API is the whole interface, as the task allows."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoints: tuple[HumanReviewCheckpoint, ...] = ()
    reviews: tuple[ReviewRecord, ...] = ()

    def open_checkpoint(self, checkpoint: HumanReviewCheckpoint) -> HumanReviewBoard:
        if checkpoint.status is not ReviewStatus.PENDING:
            raise ReviewError("a new checkpoint must start PENDING")
        return self.model_copy(update={"checkpoints": (*self.checkpoints, checkpoint)})

    def get(self, checkpoint_id: str) -> HumanReviewCheckpoint:
        for c in self.checkpoints:
            if c.checkpoint_id == checkpoint_id:
                return c
        raise ReviewError(f"unknown checkpoint_id: {checkpoint_id}")

    def review(
        self,
        checkpoint_id: str,
        decision: ReviewDecision,
        reviewer: str,
        comment: str = "",
        *,
        candidate_id: str,
        timestamp: str,
    ) -> HumanReviewBoard:
        """Record a human decision. Raises if the checkpoint is unknown or
        already decided -- a decision is recorded exactly once."""
        checkpoint = self.get(checkpoint_id)
        if checkpoint.status is not ReviewStatus.PENDING:
            raise ReviewError(
                f"checkpoint {checkpoint_id} already decided: {checkpoint.status.value}"
            )

        new_status = _DECISION_TO_STATUS[decision]
        updated = checkpoint.model_copy(update={"status": new_status})
        record = ReviewRecord(
            checkpoint_id=checkpoint_id,
            candidate_id=candidate_id,
            iteration_number=checkpoint.iteration_number,
            decision=decision,
            reviewer=reviewer,
            comment=comment,
            timestamp=timestamp,
        )
        new_checkpoints = tuple(
            updated if c.checkpoint_id == checkpoint_id else c for c in self.checkpoints
        )
        return self.model_copy(
            update={
                "checkpoints": new_checkpoints,
                "reviews": (*self.reviews, record),
            }
        )

    def pending(self) -> tuple[HumanReviewCheckpoint, ...]:
        return tuple(c for c in self.checkpoints if c.status is ReviewStatus.PENDING)

    def review_for(self, checkpoint_id: str) -> ReviewRecord | None:
        for r in self.reviews:
            if r.checkpoint_id == checkpoint_id:
                return r
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "reviews": [r.to_dict() for r in self.reviews],
        }
