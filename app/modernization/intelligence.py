"""
Phase 4 Modernization Intelligence pipeline.

Purpose:
    Compose the three Phase 4 analyzers — business rule extraction
    (#112), risk analysis (#113), and modernization strategy (#114) —
    into a single deterministic result, reusing the Phase 1–3 outputs and
    the CFG rather than recomputing them.

    The three layers stay independently testable: this module only wires
    them together in the documented order

        AnalysisResult
            -> BusinessRuleExtractor        (#112)
            -> RiskAnalyzer                  (#113, consumes the rules)
            -> ModernizationStrategyAnalyzer (#114, consumes rules + risks)

Determinism:
    Given the same :class:`~app.analysis.models.AnalysisResult` (and,
    optionally, the same :class:`~app.modernization.flow.models.Flow`),
    :func:`analyze_modernization_intelligence` returns byte-identical
    serialized output every time.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.analysis.models import AnalysisResult
from app.modernization.business_rules import BusinessRule, BusinessRuleExtractor
from app.modernization.flow.generator import generate_flow
from app.modernization.flow.models import Flow
from app.modernization.risk import ModernizationRisk, RiskAnalyzer
from app.modernization.strategy import (
    ModernizationStrategyAnalyzer,
    StrategyRecommendation,
)

__all__ = [
    "ModernizationIntelligenceResult",
    "analyze_modernization_intelligence",
]


@dataclass(frozen=True)
class ModernizationIntelligenceResult:
    """
    The combined Phase 4 output.

    Attributes:
        business_rules: Deterministically ordered rules (#112).
        risks: Deterministically ordered risks (#113).
        strategies: Deterministically ordered strategy recommendations,
            primary first (#114).
    """

    business_rules: tuple[BusinessRule, ...]
    risks: tuple[ModernizationRisk, ...]
    strategies: tuple[StrategyRecommendation, ...]

    @property
    def primary_strategy(self) -> StrategyRecommendation | None:
        for rec in self.strategies:
            if rec.is_primary:
                return rec
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a deterministic JSON-safe dictionary."""
        return {
            "business_rules": [r.to_dict() for r in self.business_rules],
            "risks": [r.to_dict() for r in self.risks],
            "strategies": [s.to_dict() for s in self.strategies],
        }


def analyze_modernization_intelligence(
    analysis_result: AnalysisResult,
    flow: Flow | None = None,
) -> ModernizationIntelligenceResult:
    """
    Run the full Phase 4 pipeline over *analysis_result*.

    Args:
        analysis_result:
            The Phase 1–3 :class:`~app.analysis.models.AnalysisResult`.
        flow:
            An already-built CFG. When ``None`` (the default) it is
            generated from ``analysis_result`` via
            :func:`~app.modernization.flow.generator.generate_flow` — the
            same function the existing modernization pipeline uses.

    Returns:
        A :class:`ModernizationIntelligenceResult`.
    """
    cfg = flow if flow is not None else generate_flow(analysis_result)

    rules = BusinessRuleExtractor().extract(analysis_result)
    risks = RiskAnalyzer().analyze(analysis_result, cfg, rules)
    strategies = ModernizationStrategyAnalyzer().analyze(
        analysis_result, cfg, rules, risks
    )

    return ModernizationIntelligenceResult(
        business_rules=tuple(rules),
        risks=tuple(risks),
        strategies=tuple(strategies),
    )
