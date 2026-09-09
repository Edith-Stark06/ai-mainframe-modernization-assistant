"""
Phase 8 #124 — AI Modernization Advisor.

Nine explicit, task-scoped operations over the deterministic Phase 1–5
analysis + #122 retrieval + a reused Phase 6/7 LLM provider. Every
response keeps DETERMINISTIC_FACT / RETRIEVED_KNOWLEDGE / AI_RECOMMENDATION
apart, verifies conclusion citations, and refuses to assert program
elements that are not in the evidence.
"""

from __future__ import annotations

from app.advisor.advisor import ModernizationAdvisor
from app.advisor.context import build as build_operation_context
from app.advisor.models import (
    AdvisorOperation,
    AdvisorResponse,
    AffectedLocation,
    Fact,
)
from app.advisor.prompt import ADVISOR_PROMPT_VERSION, build_advisor_prompt

__all__ = [
    "ModernizationAdvisor",
    "AdvisorOperation",
    "AdvisorResponse",
    "Fact",
    "AffectedLocation",
    "build_operation_context",
    "build_advisor_prompt",
    "ADVISOR_PROMPT_VERSION",
]
