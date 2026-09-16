"""
Analysis Confidence (task #116 — Phase 5).

*Analysis confidence* answers: **how trustworthy is the modernization
conclusion, given how much of the program was actually analyzed?**

It is deliberately distinct from:

* **readiness** — what the analyzed evidence suggests about modernization
  suitability (unchanged from tasks #80–#84);
* **coverage** — how much of the program was analyzed
  (:class:`~app.analysis.coverage.models.CoverageReport`).

Policy (deterministic, evidence-based — no probability, no LLM):

  base  = coverage.overall
          (coverage already measures, dimension by dimension, how much
           of the program reached each analysis stage — it is the
           natural confidence base).

  base -= semantic_penalty
          = min(0.20, semantic_error_count * 0.04)
          (semantic/type/reference errors mean the IR values behind the
           analyzed fragment may be wrong even where structural coverage
           is high — a trust problem coverage does not capture. Capped
           so it cannot dominate.)

  Then hard CEILINGS for categorical trust failures — a ceiling is
  "confidence cannot exceed X while condition Y holds", which is more
  defensible than a linear penalty and trivially monotone:

    analysis did not complete (no coverage snapshot)   -> <= 0.10
    a source region was abandoned by the parser        -> <= 0.50
    >= 5 semantic errors                                -> <= 0.65
    >= 1 semantic error                                 -> <= 0.85
    no PROCEDURE DIVISION body was analyzed             -> <= 0.50
    IR exists but no control-flow graph was produced    -> <= 0.60

  confidence = clamp(min(base, *ceilings), 0.0, 1.0)

Monotonicity (tested in the Phase 5 regression suite):

  * more unsupported syntax  -> lower coverage.overall -> lower base
  * more parser abandonment   -> lower parser coverage + 0.50 ceiling
  * more semantic errors      -> larger penalty + lower ceiling
  * more missing analysis     -> lower coverage.overall

None of these can raise confidence.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.analysis.coverage.models import CoverageReport, CoverageStatus
from app.analysis.models import AnalysisResult
from app.modernization.flow.models import Flow

__all__ = ["ConfidenceFactor", "AnalysisConfidence", "compute_confidence"]

_SEMANTIC_PENALTY_PER_ERROR = 0.04
_SEMANTIC_PENALTY_CAP = 0.20


@dataclass(frozen=True)
class ConfidenceFactor:
    """
    One influence on the confidence score.

    Attributes:
        name:
            Stable key (``"coverage"``, ``"semantic_errors"``,
            ``"parser_abandonment"`` …).
        effect:
            Signed change this factor applied to the running confidence
            (``<= 0`` for penalties; ``0`` for a ceiling that did not
            bind; negative delta for a ceiling that did bind).
        reason:
            Human explanation.
        evidence:
            Concrete counts / codes that triggered it.
    """

    name: str
    effect: float
    reason: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "effect": round(self.effect, 4),
            "reason": self.reason,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class AnalysisConfidence:
    """
    How trustworthy the modernization conclusion is.

    Attributes:
        score:
            ``0.0``–``1.0``. High only when the pipeline has strong
            evidence it actually analyzed the program.
        factors:
            Every factor considered, in application order, each with the
            effect it had.
        detail:
            One-line summary.
    """

    score: float
    factors: tuple[ConfidenceFactor, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                f"AnalysisConfidence score must be in [0.0, 1.0], got {self.score!r}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "factors": [f.to_dict() for f in self.factors],
            "detail": self.detail,
        }


def compute_confidence(
    coverage: CoverageReport,
    analysis_result: AnalysisResult,
    flow: Flow | None = None,
) -> AnalysisConfidence:
    """Deterministically derive :class:`AnalysisConfidence`. See module docstring."""
    factors: list[ConfidenceFactor] = []

    base = coverage.overall
    factors.append(
        ConfidenceFactor(
            name="coverage",
            effect=base - 1.0,
            reason="Confidence starts from overall analysis coverage.",
            evidence=(
                f"coverage.overall={round(base, 4)}",
                f"coverage.overall_status={coverage.overall_status.value}",
            ),
        )
    )

    running = base

    sem_errors = len(analysis_result.semantic_diagnostics)
    if sem_errors:
        penalty = min(_SEMANTIC_PENALTY_CAP, sem_errors * _SEMANTIC_PENALTY_PER_ERROR)
        new = max(0.0, running - penalty)
        factors.append(
            ConfidenceFactor(
                name="semantic_errors",
                effect=new - running,
                reason=(
                    "Semantic/type/reference errors mean the analyzed IR values "
                    "may be wrong even where structural coverage is high."
                ),
                evidence=(f"{sem_errors} semantic diagnostic(s)",),
            )
        )
        running = new

    # -- ceilings ------------------------------------------------------------
    ceilings: list[tuple[float, str, tuple[str, ...]]] = []

    if analysis_result.coverage is None:
        ceilings.append(
            (
                0.10,
                "Analysis did not complete — no coverage snapshot was produced "
                "(lexer or top-level parser failure).",
                (),
            )
        )

    cov = analysis_result.coverage
    if cov is not None and cov.abandoned_construct_count > 0:
        ceilings.append(
            (
                0.50,
                "The parser abandoned one or more regions of the source; the "
                "content of those regions is unknown.",
                (f"{cov.abandoned_construct_count} abandoned region(s)",),
            )
        )

    if sem_errors >= 5:
        ceilings.append(
            (0.65, "Five or more semantic errors.", (f"{sem_errors} errors",))
        )
    elif sem_errors >= 1:
        ceilings.append(
            (0.85, "One or more semantic errors.", (f"{sem_errors} errors",))
        )

    ast = analysis_result.ast
    no_proc_body = ast is not None and (
        ast.procedure_division is None or not ast.procedure_division.paragraphs
    )
    if no_proc_body:
        ceilings.append(
            (
                0.50,
                "No PROCEDURE DIVISION body was analyzed — there is no behavioural "
                "evidence for a modernization conclusion.",
                (),
            )
        )

    if (
        analysis_result.ir is not None
        and coverage.control_flow.status is CoverageStatus.FAILED
    ):
        ceilings.append(
            (
                0.60,
                "IR exists but no control-flow graph was produced — control flow "
                "is unverified.",
                (),
            )
        )

    for cap, reason, evidence in ceilings:
        if running > cap:
            factors.append(
                ConfidenceFactor(
                    name="ceiling",
                    effect=cap - running,
                    reason=reason,
                    evidence=evidence,
                )
            )
            running = cap
        else:
            factors.append(
                ConfidenceFactor(
                    name="ceiling",
                    effect=0.0,
                    reason=f"(not binding) {reason}",
                    evidence=evidence,
                )
            )

    score = max(0.0, min(1.0, running))

    if score >= 0.85:
        detail = "High — the pipeline has strong evidence it analyzed the program."
    elif score >= 0.6:
        detail = "Moderate — meaningful gaps in the analysis; treat with caution."
    elif score >= 0.3:
        detail = "Low — large portions of the program were not analyzed."
    else:
        detail = "Very low — the program was barely analyzed or analysis failed."

    return AnalysisConfidence(score=score, factors=tuple(factors), detail=detail)
