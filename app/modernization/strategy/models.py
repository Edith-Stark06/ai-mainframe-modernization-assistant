"""
Modernization Strategy Models (task #114 — Phase 4 Modernization Intelligence).

Purpose:
    Define the structured, immutable representation of a *modernization
    strategy recommendation* produced deterministically from parser
    coverage, the AST/IR, the CFG, dependency analysis, the Phase 4
    business rules, and the Phase 4 risks.

    Selection is rule-based and evidence-driven — there is no scoring
    threshold and no LLM. See
    :class:`~app.modernization.strategy.analyzer.ModernizationStrategyAnalyzer`
    for the decision rules.

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
    "ModernizationStrategy",
    "StrategyRecommendation",
    "STRATEGY_PRECEDENCE",
]


@unique
class ModernizationStrategy(Enum):
    """The supported modernization strategies."""

    REHOST = "REHOST"
    REFACTOR = "REFACTOR"
    REPLATFORM = "REPLATFORM"
    REWRITE = "REWRITE"
    STRANGLER_MODERNIZATION = "STRANGLER_MODERNIZATION"
    SERVICE_EXTRACTION = "SERVICE_EXTRACTION"
    PHASED_MIGRATION = "PHASED_MIGRATION"


#: Deterministic precedence — most decisive / disruptive first. Used to
#: pick the single primary recommendation and to order the output.
STRATEGY_PRECEDENCE: dict[ModernizationStrategy, int] = {
    ModernizationStrategy.REWRITE: 0,
    ModernizationStrategy.PHASED_MIGRATION: 1,
    ModernizationStrategy.STRANGLER_MODERNIZATION: 2,
    ModernizationStrategy.SERVICE_EXTRACTION: 3,
    ModernizationStrategy.REPLATFORM: 4,
    ModernizationStrategy.REFACTOR: 5,
    ModernizationStrategy.REHOST: 6,
}


@dataclass(frozen=True)
class StrategyRecommendation:
    """
    A single, evidence-backed modernization strategy recommendation.

    Attributes:
        recommendation_id:
            Stable identifier (``STRAT-NNN``) assigned by the analyzer
            after a total deterministic sort.
        strategy:
            The recommended :class:`ModernizationStrategy`.
        is_primary:
            ``True`` for exactly one recommendation — the highest-
            precedence strategy whose decision rule fired.
        rationale:
            Why this strategy fits, in plain terms. Distinct per
            strategy.
        evidence:
            The concrete analysis facts that triggered the rule
            (paragraph counts, dependency counts, risk severities …).
            Never empty.
        referenced_risk_ids:
            IDs of the :class:`~app.modernization.risk.models.ModernizationRisk`
            records that form part of this recommendation's evidence.
        prerequisites:
            Actionable, evidence-based steps to take before executing the
            strategy.
        confidence:
            ``1.0`` when the decisive evidence includes an explicit
            diagnostic-derived risk or a direct dependency edge; ``0.8``
            when it rests on structural counts; ``0.5`` for the
            no-analyzable-logic fallback. Never probabilistic.

    Raises:
        ValueError: if ``rationale`` or ``evidence`` is empty, or
            ``confidence`` is outside ``[0.0, 1.0]``.
    """

    recommendation_id: str
    strategy: ModernizationStrategy
    is_primary: bool
    rationale: str
    evidence: tuple[str, ...]
    referenced_risk_ids: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    confidence: float = 0.8

    def __post_init__(self) -> None:
        if not self.rationale or not self.rationale.strip():
            raise ValueError("StrategyRecommendation rationale cannot be empty.")
        if not self.evidence:
            raise ValueError(
                "StrategyRecommendation must carry at least one evidence item."
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"StrategyRecommendation confidence must be within [0.0, 1.0], "
                f"got {self.confidence!r}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a deterministic JSON-safe dictionary."""
        return {
            "recommendation_id": self.recommendation_id,
            "strategy": self.strategy.value,
            "is_primary": self.is_primary,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "referenced_risk_ids": list(self.referenced_risk_ids),
            "prerequisites": list(self.prerequisites),
            "confidence": self.confidence,
        }
