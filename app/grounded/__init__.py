"""
Phase 8 #123 — modernization-aware grounded chat.

Every context item carries provenance; the model's citations are
verified against that context; a factual answer with no grounded
evidence becomes "cannot be determined from the available evidence".
"""

from __future__ import annotations

from app.grounded.builder import build_context_from_bundle
from app.grounded.chat import GroundedChat, GroundedChatResult
from app.grounded.context import Basis, ContextItem, GroundedContext
from app.grounded.errors import (
    AnswerParseError,
    ContextProvenanceError,
    GroundedChatError,
)
from app.grounded.models import ConfidenceBand, EvidenceRef, GroundedAnswer
from app.grounded.parsing import parse_and_verify
from app.grounded.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_grounded_prompt

__all__ = [
    "GroundedChat",
    "GroundedChatResult",
    "GroundedContext",
    "ContextItem",
    "Basis",
    "GroundedAnswer",
    "EvidenceRef",
    "ConfidenceBand",
    "build_context_from_bundle",
    "build_grounded_prompt",
    "parse_and_verify",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "GroundedChatError",
    "ContextProvenanceError",
    "AnswerParseError",
]
