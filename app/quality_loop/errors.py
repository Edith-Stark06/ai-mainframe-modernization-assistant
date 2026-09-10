"""Exceptions for the Phase 11 quality loop."""

from __future__ import annotations


class QualityLoopError(Exception):
    """Base class for every Phase 11 error."""


class InvalidStateTransitionError(QualityLoopError):
    """The requested :class:`LoopState` transition is not allowed."""


class ReviewError(QualityLoopError):
    """A human-review action was invalid (unknown checkpoint, already decided, …)."""


__all__ = ["QualityLoopError", "InvalidStateTransitionError", "ReviewError"]
