"""Exceptions for Phase 8 #123 grounded chat."""

from __future__ import annotations

from app.knowledge.errors import KnowledgeError


class GroundedChatError(KnowledgeError):
    """Base class for grounded-chat errors."""


class ContextProvenanceError(GroundedChatError):
    """A context item was about to be sent to the model without provenance.

    Hard boundary: the context is rejected, never truncated-and-sent.
    """


class AnswerParseError(GroundedChatError):
    """The model response could not be parsed into a structured answer."""


__all__ = ["GroundedChatError", "ContextProvenanceError", "AnswerParseError"]
