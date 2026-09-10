"""Exceptions for the Phase 10 behavioral-equivalence pipeline (#129-#131)."""

from __future__ import annotations


class BehavioralError(Exception):
    """Base class for every Phase 10 error."""


class ExtractionError(BehavioralError):
    """A behavioral test case could not be derived from the analysis."""


class JavaTestGenerationError(BehavioralError):
    """A Java test artifact could not be derived from a behavioral test case."""


class ExecutionSetupError(BehavioralError):
    """An execution workspace / command could not be prepared safely.

    Raised for path traversal, an unavailable runtime the caller demanded,
    etc. A *runtime being genuinely unavailable* (no GnuCOBOL) is NOT this
    — that is reported as ``ExecutionResult(executed=False, ...)`` so the
    pipeline degrades to INCONCLUSIVE instead of crashing.
    """


__all__ = [
    "BehavioralError",
    "ExtractionError",
    "JavaTestGenerationError",
    "ExecutionSetupError",
]
