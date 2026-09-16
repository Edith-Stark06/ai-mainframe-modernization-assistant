"""
Repair eligibility (Phase 11).

A deterministic gate that decides — before any LLM is ever invoked —
whether a :class:`~app.quality_loop.failure.FailureRecord` is even a
*candidate* for AI-proposed repair. This is separate from confidence
scoring: eligibility asks "is it structurally possible to attempt a
targeted repair here", confidence asks "how much evidence backs the
specific patch that was proposed".

Never eligible: COBOL runtime unavailable / DB2 / CICS / VSAM
unavailable (surfaces as ``INFRASTRUCTURE_FAILURE``), missing source
mapping (surfaces as ``PROVENANCE_FAILURE`` — already normalized by
:func:`app.quality_loop.failure.classify_failures`), unsupported COBOL
semantics (``UNSUPPORTED_BEHAVIOR``). These always route to
HUMAN_REVIEW or stay INCONCLUSIVE — never a speculative AI change.
"""

from __future__ import annotations

from app.quality_loop.failure import NEVER_AUTO_REPAIRED, FailureCategory, FailureRecord

__all__ = ["repair_eligibility"]

_REPAIRABLE_CATEGORIES = frozenset(
    {
        FailureCategory.COMPILATION_ERROR,
        FailureCategory.TEST_FAILURE,
        FailureCategory.EXECUTION_FAILURE,
        FailureCategory.BEHAVIORAL_MISMATCH,
    }
)


def repair_eligibility(failure: FailureRecord) -> tuple[bool, str]:
    """Deterministic yes/no + documented reason. Never influenced by the LLM."""
    if failure.category in NEVER_AUTO_REPAIRED:
        return (
            False,
            f"{failure.category.value} is never auto-repaired -> requires human review "
            "or remains INCONCLUSIVE",
        )
    if failure.category not in _REPAIRABLE_CATEGORIES:
        return False, f"{failure.category.value} has no defined repair strategy"
    if failure.source_mapping is None:
        return False, "no source mapping -> provenance insufficient for targeted repair"
    if failure.source_mapping.source_path is None:
        return (
            False,
            "source mapping lacks a source_path -> cannot ground a targeted repair",
        )
    return True, "eligible: deterministic evidence present (category + source mapping)"
