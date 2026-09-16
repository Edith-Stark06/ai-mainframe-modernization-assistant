"""
Business Rule Extraction (task #112 — Phase 4 Modernization Intelligence).

Deterministic, evidence-based extraction of business rules from the
Phase 1–3 analysis outputs. See :mod:`.extractor` and :mod:`.models`.
"""

from app.modernization.business_rules.extractor import (
    BusinessRuleExtractor,
    classify_rule,
)
from app.modernization.business_rules.models import (
    BusinessRule,
    BusinessRuleCategory,
    RuleAction,
    RuleActionKind,
    RuleVariables,
)

__all__ = [
    "BusinessRule",
    "BusinessRuleCategory",
    "BusinessRuleExtractor",
    "RuleAction",
    "RuleActionKind",
    "RuleVariables",
    "classify_rule",
]
