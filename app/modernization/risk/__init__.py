"""
Risk Analysis (task #113 — Phase 4 Modernization Intelligence).

Deterministic, evidence-based detection of modernization risks from the
Phase 1–3 analysis outputs, the CFG, and the Phase 4 business rules.
See :mod:`.analyzer` and :mod:`.models`.
"""

from app.modernization.risk.analyzer import RiskAnalyzer
from app.modernization.risk.models import (
    SEVERITY_ORDER,
    ModernizationRisk,
    RiskCategory,
    RiskSeverity,
)

__all__ = [
    "ModernizationRisk",
    "RiskAnalyzer",
    "RiskCategory",
    "RiskSeverity",
    "SEVERITY_ORDER",
]
