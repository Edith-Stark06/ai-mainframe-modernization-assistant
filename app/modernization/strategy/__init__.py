"""
Modernization Strategy (task #114 — Phase 4 Modernization Intelligence).

Deterministic, evidence-based modernization strategy recommendations
built from parser coverage, the AST/IR/CFG, dependency analysis, the
Phase 4 business rules, and the Phase 4 risks. See :mod:`.analyzer` and
:mod:`.models`.
"""

from app.modernization.strategy.analyzer import ModernizationStrategyAnalyzer
from app.modernization.strategy.models import (
    STRATEGY_PRECEDENCE,
    ModernizationStrategy,
    StrategyRecommendation,
)

__all__ = [
    "ModernizationStrategy",
    "ModernizationStrategyAnalyzer",
    "StrategyRecommendation",
    "STRATEGY_PRECEDENCE",
]
