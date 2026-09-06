"""
Confidence-Aware Scoring (task #116 — Phase 5).

``score_with_confidence`` composes the three orthogonal concepts into one
result object without changing any of them:

* **readiness / complexity / coupling** — exactly what
  :func:`app.modernization.scoring.service.calculate_scores` produced
  before Phase 5 (the #80–#84 contract). Not penalised by confidence.
* **analysis_coverage** — ``CoverageReport.overall`` (#115).
* **analysis_confidence** — ``AnalysisConfidence.score`` (#116).

The critical property: a program can legitimately be

    readiness = 0.92,  confidence = 0.38,  coverage = 0.41

when the analysed fragment looks simple but most of the program was not
understood. The output makes the three numbers, and their meaning,
explicit so an incomplete high-readiness score is never mistaken for a
high-confidence recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.analysis.coverage import compute_coverage
from app.analysis.coverage.models import CoverageReport
from app.analysis.models import AnalysisResult
from app.modernization.business_rules import BusinessRuleExtractor
from app.modernization.flow.generator import generate_flow
from app.modernization.flow.models import Flow
from app.modernization.scoring.confidence import AnalysisConfidence, compute_confidence
from app.modernization.scoring.models import ModernizationScore
from app.modernization.scoring.service import calculate_scores

__all__ = ["ConfidenceAwareScore", "score_with_confidence"]


@dataclass(frozen=True)
class ConfidenceAwareScore:
    """
    Readiness, confidence and coverage, kept explicitly separate.

    Attributes:
        readiness:
            ``ModernizationScore.overall_readiness`` — unchanged from
            #80–#84. What the *analysed* evidence suggests about
            modernization suitability.
        complexity / coupling:
            ``ModernizationScore.complexity_score`` /
            ``.coupling_score`` — unchanged.
        analysis_confidence:
            How trustworthy ``readiness`` is given how much was analysed.
        analysis_coverage:
            ``CoverageReport.overall`` — how much of the program was
            analysed.
        insufficient_data:
            ``True`` when the underlying flow had nothing to score
            (propagated from the existing scorer).
        interpretation:
            One-line plain-English reading of the readiness/confidence/
            coverage combination.
        score / coverage_report / confidence:
            The full underlying objects.
    """

    readiness: float
    complexity: float
    coupling: float
    analysis_confidence: float
    analysis_coverage: float
    insufficient_data: bool
    interpretation: str
    score: ModernizationScore
    coverage_report: CoverageReport
    confidence: AnalysisConfidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness": round(self.readiness, 4),
            "complexity": round(self.complexity, 4),
            "coupling": round(self.coupling, 4),
            "analysis_confidence": round(self.analysis_confidence, 4),
            "analysis_coverage": round(self.analysis_coverage, 4),
            "insufficient_data": self.insufficient_data,
            "interpretation": self.interpretation,
            "coverage": self.coverage_report.to_dict(),
            "confidence": self.confidence.to_dict(),
            "score": self.score.to_dict(),
        }


def _interpret(
    readiness: float,
    confidence: float,
    coverage: float,
    *,
    no_procedure_body: bool,
    analysis_failed: bool,
) -> str:
    if analysis_failed:
        return (
            "Analysis failed or barely completed. Readiness, confidence and "
            "coverage are all near zero; there is no basis for a modernization "
            "conclusion."
        )
    if no_procedure_body:
        return (
            "The program has no PROCEDURE DIVISION body. There is no behaviour "
            "to modernize and no basis for a confident readiness figure — "
            "coverage is 'complete' only because there was nothing to analyse."
        )
    if confidence >= 0.8 and coverage >= 0.8:
        if readiness >= 0.7:
            return (
                "The program was thoroughly analysed and the evidence supports "
                "modernization."
            )
        return (
            "The program was thoroughly analysed; the evidence indicates "
            "modernization will need real work."
        )
    if confidence < 0.4 or coverage < 0.4:
        return (
            "Most of the program was NOT analysed. The readiness figure reflects "
            "only the small analysed fragment and must not be read as a "
            "high-confidence recommendation."
        )
    return (
        "The program was partially analysed. Readiness reflects the analysed "
        "portion; confidence and coverage show how much is still unknown."
    )


def score_with_confidence(
    analysis_result: AnalysisResult,
    flow: Flow | None = None,
) -> ConfidenceAwareScore:
    """
    Run coverage (#115) + confidence (#116) alongside the existing scorer.

    Args:
        analysis_result: Phase 1–4 pipeline output.
        flow: An already-built CFG. When ``None`` it is generated via
            :func:`~app.modernization.flow.generator.generate_flow` (the
            same function the existing modernization pipeline uses).
    """
    cfg = flow if flow is not None else generate_flow(analysis_result)
    rules = BusinessRuleExtractor().extract(analysis_result)

    coverage_report = compute_coverage(analysis_result, cfg, rules)
    confidence = compute_confidence(coverage_report, analysis_result, cfg)
    score = calculate_scores(analysis_result, cfg)

    ast = analysis_result.ast
    no_procedure_body = bool(
        ast is not None
        and (ast.procedure_division is None or not ast.procedure_division.paragraphs)
    )
    analysis_failed = analysis_result.coverage is None or (
        coverage_report.overall_status.name == "FAILED"
    )
    # Our own richer "nothing meaningful to score" signal: the existing
    # scorer only flags a literally empty flow graph, which misses a
    # parsed-but-bodyless program (whose call-graph still has one node).
    insufficient = bool(
        score.metadata.get("insufficient_data") or no_procedure_body or analysis_failed
    )
    interpretation = _interpret(
        score.overall_readiness,
        confidence.score,
        coverage_report.overall,
        no_procedure_body=no_procedure_body,
        analysis_failed=analysis_failed,
    )

    return ConfidenceAwareScore(
        readiness=score.overall_readiness,
        complexity=score.complexity_score,
        coupling=score.coupling_score,
        analysis_confidence=confidence.score,
        analysis_coverage=coverage_report.overall,
        insufficient_data=insufficient,
        interpretation=interpretation,
        score=score,
        coverage_report=coverage_report,
        confidence=confidence,
    )
