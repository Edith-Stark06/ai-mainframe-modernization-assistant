"""
Modernization Risk Models (task #113 — Phase 4 Modernization Intelligence).

Purpose:
    Define the structured, immutable representation of a *modernization
    risk* detected deterministically from the Phase 1–3 analysis outputs
    plus the Phase 4 business rules.

    Every risk is evidence-backed: it answers *what was detected*, *why it
    is a modernization risk*, *what analysis evidence proves it*, *which
    component is affected*, and *what to do about it*. No risk is emitted
    without concrete AST / IR / CFG / dependency / parser-diagnostic
    evidence, and there is no numeric "risk score".

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Any

from app.analysis.serializers._common import serialize_value
from app.parser.lexer.position import Position

__all__ = [
    "RiskCategory",
    "RiskSeverity",
    "ModernizationRisk",
    "SEVERITY_ORDER",
]


@unique
class RiskCategory(Enum):
    """
    The kind of modernization risk. Each value maps to exactly one
    detector in :class:`~app.modernization.risk.analyzer.RiskAnalyzer`.
    """

    UNSUPPORTED_SYNTAX = "UNSUPPORTED_SYNTAX"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    PARSER_COVERAGE_GAP = "PARSER_COVERAGE_GAP"
    EXTERNAL_CALL = "EXTERNAL_CALL"
    UNRESOLVED_PERFORM_TARGET = "UNRESOLVED_PERFORM_TARGET"
    COMPLEX_CONTROL_FLOW = "COMPLEX_CONTROL_FLOW"
    DEEPLY_NESTED_CONDITIONS = "DEEPLY_NESTED_CONDITIONS"
    SHARED_MUTABLE_STATE = "SHARED_MUTABLE_STATE"
    UNDOCUMENTED_BUSINESS_RULES = "UNDOCUMENTED_BUSINESS_RULES"
    DATA_COMPLEXITY = "DATA_COMPLEXITY"


@unique
class RiskSeverity(Enum):
    """
    Ordinal severity. The ordinal is a *sort key only* — it is never
    combined arithmetically into a score.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


#: Deterministic ordering from most to least severe (used for sorting).
SEVERITY_ORDER: dict[RiskSeverity, int] = {
    RiskSeverity.CRITICAL: 0,
    RiskSeverity.HIGH: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.LOW: 3,
}


@dataclass(frozen=True)
class ModernizationRisk:
    """
    A single, evidence-backed modernization risk.

    Attributes:
        risk_id:
            Stable identifier (``RISK-<category-slug>-NNN``) assigned by
            the analyzer after a total deterministic sort.
        category:
            The risk kind — see :class:`RiskCategory`.
        severity:
            ``LOW`` / ``MEDIUM`` / ``HIGH`` / ``CRITICAL`` from the
            documented per-category policy in
            :class:`~app.modernization.risk.analyzer.RiskAnalyzer`.
        title:
            Short fixed label for the category/instance.
        explanation:
            Why this is a modernization risk, in plain terms.
        evidence:
            The concrete analysis facts that prove the risk — diagnostic
            codes and messages, dependency edges, CFG counts, etc. Never
            empty.
        source_locations:
            Positions in the source the risk points at. May be empty for
            a genuinely program-wide risk.
        affected_components:
            Paragraph names, ``"DATA DIVISION"``, or ``"<program>"`` —
            whatever the evidence attributes the risk to.
        confidence:
            ``1.0`` when derived directly from an explicit diagnostic or
            a direct dependency/CFG fact; ``0.75`` when derived from a
            structural heuristic over the AST/CFG. Never probabilistic.
        recommended_mitigation:
            A concrete, actionable next step.
        occurrence_count:
            How many underlying occurrences this (aggregated) risk
            represents. ``1`` for non-aggregated risks.

    Raises:
        ValueError: if ``evidence`` is empty, ``explanation`` is empty, or
            ``confidence`` is outside ``[0.0, 1.0]``.
    """

    risk_id: str
    category: RiskCategory
    severity: RiskSeverity
    title: str
    explanation: str
    evidence: tuple[str, ...]
    source_locations: tuple[Position, ...] = ()
    affected_components: tuple[str, ...] = ()
    confidence: float = 1.0
    recommended_mitigation: str = ""
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError("ModernizationRisk must carry at least one evidence item.")
        if not self.explanation or not self.explanation.strip():
            raise ValueError("ModernizationRisk explanation cannot be empty.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"ModernizationRisk confidence must be within [0.0, 1.0], "
                f"got {self.confidence!r}."
            )
        if self.occurrence_count < 1:
            raise ValueError("ModernizationRisk occurrence_count must be >= 1.")

    def dedup_key(self) -> tuple[str, str, tuple[str, ...]]:
        """Structural identity: category + title + sorted affected components."""
        return (
            self.category.value,
            self.title,
            tuple(sorted(self.affected_components)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a deterministic JSON-safe dictionary."""
        return {
            "risk_id": self.risk_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "explanation": self.explanation,
            "evidence": list(self.evidence),
            "source_locations": [serialize_value(p) for p in self.source_locations],
            "affected_components": list(self.affected_components),
            "confidence": self.confidence,
            "recommended_mitigation": self.recommended_mitigation,
            "occurrence_count": self.occurrence_count,
        }
