"""Structured advisor response (#124) — fact / retrieval / recommendation kept apart."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.grounded.models import ConfidenceBand, EvidenceRef
from app.knowledge.provenance import Provenance

__all__ = ["AdvisorOperation", "Fact", "AffectedLocation", "AdvisorResponse"]


class AdvisorOperation(str, Enum):
    EXPLAIN_PROGRAM = "explain_program"
    EXPLAIN_PARAGRAPH = "explain_paragraph"
    EXPLAIN_BUSINESS_RULE = "explain_business_rule"
    IDENTIFY_RISKS = "identify_risks"
    RECOMMEND_STRATEGY = "recommend_strategy"
    EXPLAIN_DEPENDENCIES = "explain_dependencies"
    PROPOSE_JAVA_ARCHITECTURE = "propose_java_architecture"
    REVIEW_GENERATED_JAVA = "review_generated_java"
    ANSWER_MIGRATION_QUESTION = "answer_migration_question"


class Fact(BaseModel):
    """A deterministic fact produced by Phase 1–5 analysis — NOT by the LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement: str
    basis: str = "DETERMINISTIC_FACT"
    provenance: Provenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "basis": self.basis,
            "citation": self.provenance.citation(),
            "provenance": self.provenance.model_dump(mode="json"),
        }


class AffectedLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    source_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    paragraph: str | None = None


class AdvisorResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: AdvisorOperation
    #: grounded, evidence-backed statement of what the analysis shows
    conclusion: str
    #: deterministic facts the advisor built the context from
    facts: tuple[Fact, ...] = ()
    #: verified citations behind ``conclusion`` (DETERMINISTIC_FACT / RETRIEVED_KNOWLEDGE)
    evidence: tuple[EvidenceRef, ...] = ()
    retrieved_knowledge: tuple[EvidenceRef, ...] = ()
    #: the model's modernization advice — basis AI_RECOMMENDATION, never a fact
    recommendation: str = ""
    #: evidence-coverage band, NOT a calibrated probability
    confidence: ConfidenceBand = ConfidenceBand.NONE
    affected_source_locations: tuple[AffectedLocation, ...] = ()
    basis_summary: dict[str, int] = Field(default_factory=dict)
    insufficient_evidence: bool = True
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "conclusion": self.conclusion,
            "facts": [f.to_dict() for f in self.facts],
            "evidence": [e.model_dump(mode="json") for e in self.evidence],
            "retrieved_knowledge": [
                e.model_dump(mode="json") for e in self.retrieved_knowledge
            ],
            "recommendation": self.recommendation,
            "recommendation_basis": "AI_RECOMMENDATION",
            "confidence": self.confidence.value,
            "affected_source_locations": [
                a.model_dump(mode="json") for a in self.affected_source_locations
            ],
            "basis_summary": self.basis_summary,
            "insufficient_evidence": self.insufficient_evidence,
            "notes": list(self.notes),
        }
