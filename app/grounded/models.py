"""Structured grounded-chat answer (#123)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ConfidenceBand", "EvidenceRef", "GroundedAnswer"]


class ConfidenceBand(str, Enum):
    """Application-level evidence coverage — NOT a calibrated probability."""

    HIGH = "high_evidence_coverage"
    MODERATE = "moderate_evidence_coverage"
    LOW = "low_evidence_coverage"
    NONE = "no_supporting_evidence"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    basis: str
    source_id: str
    citation: str
    source_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    paragraph: str | None = None
    rule_id: str | None = None
    risk_id: str | None = None


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    evidence: tuple[EvidenceRef, ...] = ()
    #: coarse band; ``confidence_value`` is a derived number, not a probability
    confidence: ConfidenceBand = ConfidenceBand.NONE
    confidence_value: float = Field(0.0, ge=0.0, le=1.0)
    insufficient_context: bool = True
    #: model claims the verifier stripped because they were not grounded
    rejected_claims: tuple[str, ...] = ()
    basis_breakdown: dict[str, int] = Field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "evidence": [e.model_dump(mode="json") for e in self.evidence],
            "confidence": self.confidence.value,
            "confidence_value": self.confidence_value,
            "insufficient_context": self.insufficient_context,
            "rejected_claims": list(self.rejected_claims),
            "basis_breakdown": self.basis_breakdown,
            "notes": list(self.notes),
        }
