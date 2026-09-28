"""
Cloud Readiness Models (task #stage48 — Phase 7 Modernization Intelligence).

Purpose:
    Define the structured, immutable representation of a *cloud
    readiness assessment*: how tightly a COBOL program is coupled to
    mainframe-specific execution/data technology (CICS transaction
    processing, DB2/EXEC SQL, IMS/DL-I, VSAM indexed/relative file
    organization) that has no drop-in cloud equivalent, plus the same
    structural risk signals :mod:`app.modernization.risk` already
    computes (external CALL coupling, unsupported/unmodelled syntax,
    control-flow complexity).

    Matching :mod:`app.modernization.strategy`'s own explicit design
    choice: assignment to a tier is rule-based and evidence-driven —
    there is no numeric "cloud readiness score" and no LLM. A score
    invites exactly the kind of unhonest precision this project's risk
    and strategy layers deliberately reject (see their own module
    docstrings) -- two files with wildly different technical realities
    could tie at "72/100" with no way to tell why. A tier with cited
    evidence cannot.

Responsibilities:
    - :class:`CloudReadinessTier` -- the four-value, precedence-ordered
      tier enum.
    - :data:`TIER_PRECEDENCE` -- deterministic most-severe-first
      ordering used to resolve ties between rules.
    - :class:`CloudReadinessAssessment` -- the immutable, validated
      result: tier, rationale, cited evidence, prerequisites, confidence.

Non-responsibilities:
    - Computing the assessment itself (belongs to
      :class:`~app.modernization.cloud.analyzer.CloudReadinessAnalyzer`).

Dependencies:
    - Python standard library (dataclasses, enum, typing).

Examples:
    Constructing an assessment directly::

        from app.modernization.cloud.models import (
            CloudReadinessAssessment,
            CloudReadinessTier,
        )

        assessment = CloudReadinessAssessment(
            tier=CloudReadinessTier.CLOUD_READY,
            rationale="No mainframe-specific coupling detected.",
            evidence=("No EXEC SQL/CICS/DLI or VSAM signals found.",),
        )
        assert assessment.to_dict()["tier"] == "CLOUD_READY"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Any

__all__ = [
    "CloudReadinessAssessment",
    "CloudReadinessTier",
    "TIER_PRECEDENCE",
]


@unique
class CloudReadinessTier(Enum):
    """
    How ready a single COBOL program is for cloud migration, from most
    to least coupled to mainframe-specific technology.

    Attributes:
        NOT_RECOMMENDED:
            Deep coupling to multiple mainframe-specific subsystems at
            once (e.g. both CICS and IMS/DL-I), or a parser coverage gap
            severe enough that the rest of this assessment cannot be
            trusted. Migrating as-is is not advisable; a full rewrite
            against the target platform is the realistic path.
        REQUIRES_REARCHITECTURE:
            Coupled to one mainframe-specific execution or data
            subsystem with no drop-in cloud equivalent (CICS
            transaction processing, IMS/DL-I hierarchical database, or
            VSAM indexed/relative file access). The data or transaction
            layer needs redesigning, not just relocating.
        NEEDS_REFACTORING:
            Uses portable-but-coupled technology (EXEC SQL/DB2, which
            most clouds offer a relational equivalent for) and/or a
            meaningful external integration surface (multiple external
            CALL targets). Migration is feasible with moderate,
            targeted refactoring.
        CLOUD_READY:
            No detected mainframe-specific data/transaction coupling,
            a small integration surface, and a parser that reached
            every statement. The most straightforward rehost/replatform
            candidate this assessment can identify.
    """

    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    REQUIRES_REARCHITECTURE = "REQUIRES_REARCHITECTURE"
    NEEDS_REFACTORING = "NEEDS_REFACTORING"
    CLOUD_READY = "CLOUD_READY"


#: Deterministic precedence — most severe first. Used to pick the single
#: tier when more than one rule's evidence is present at once.
TIER_PRECEDENCE: dict[CloudReadinessTier, int] = {
    CloudReadinessTier.NOT_RECOMMENDED: 0,
    CloudReadinessTier.REQUIRES_REARCHITECTURE: 1,
    CloudReadinessTier.NEEDS_REFACTORING: 2,
    CloudReadinessTier.CLOUD_READY: 3,
}


@dataclass(frozen=True)
class CloudReadinessAssessment:
    """
    A single, evidence-backed cloud readiness assessment for one COBOL
    program.

    Attributes:
        tier:
            The assigned :class:`CloudReadinessTier`.
        rationale:
            Why this tier fits, in plain terms.
        evidence:
            The concrete analysis facts that triggered the rule
            (``EXEC CICS`` occurrence counts, VSAM organization
            clauses, external CALL counts, ...), each citing a source
            line when the underlying signal has one. Never empty.
        prerequisites:
            Actionable, evidence-based steps to take before migration.
        confidence:
            ``1.0`` when every decisive signal comes from an explicit,
            unambiguous source-text match (``EXEC CICS``, ``ORGANIZATION
            IS INDEXED``, ...); lower when the parser could not fully
            analyse the source, since an under-analysed program's true
            coupling may be worse than what was detected. Never
            probabilistic.

    Raises:
        ValueError: if ``rationale`` or ``evidence`` is empty, or
            ``confidence`` is outside ``[0.0, 1.0]``.
    """

    tier: CloudReadinessTier
    rationale: str
    evidence: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.rationale or not self.rationale.strip():
            raise ValueError("CloudReadinessAssessment rationale cannot be empty.")
        if not self.evidence:
            raise ValueError(
                "CloudReadinessAssessment must carry at least one evidence item."
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"CloudReadinessAssessment confidence must be within [0.0, 1.0], "
                f"got {self.confidence!r}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a deterministic JSON-safe dictionary."""
        return {
            "tier": self.tier.value,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "prerequisites": list(self.prerequisites),
            "confidence": self.confidence,
        }
