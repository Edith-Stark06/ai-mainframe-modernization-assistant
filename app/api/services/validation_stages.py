"""
Classify already-computed Phase 1-11 artifacts into the Validation
Center's explicit PASS / FAIL / INCONCLUSIVE / NOT_AVAILABLE vocabulary.

Shared by the Validation Center and Report API routes so both report
identical stage verdicts from identical inputs -- one implementation,
not two. Every function here is pure and deterministic: no network
call, no re-analysis, no LLM.
"""

from __future__ import annotations

from app.api.schemas.validation import CORE_STAGES, StageResult, StageStatus
from app.behavioral.comparison.models import OverallStatus
from app.dataset.analysis_bundle import AnalysisBundle
from app.dataset.modernization_bundle import ModernizationBundle

__all__ = ["compute_validation_stages", "compute_overall_status"]

_SELF_REPAIR_REASON = (
    "AI provider not configured -- app.api.dependencies.ai.get_llm_provider() "
    "returns None in this environment, so the Phase 11 quality/self-repair "
    "loop was never invoked. No repair history exists for this analysis."
)


def _parser_stage(bundle: AnalysisBundle) -> StageResult:
    errors = [d for d in bundle.syntax_diagnostics if d.get("severity") == "ERROR"]
    if bundle.ast is None:
        return StageResult(
            stage="Parser",
            status=StageStatus.FAIL,
            summary="The parser did not produce a usable AST.",
            details={"syntax_diagnostics": bundle.syntax_diagnostics},
        )
    if errors:
        return StageResult(
            stage="Parser",
            status=StageStatus.FAIL,
            summary=f"{len(errors)} parser error(s) reported.",
            details={"errors": errors},
        )
    return StageResult(
        stage="Parser",
        status=StageStatus.PASS,
        summary="No parser errors.",
        details={"diagnostic_count": len(bundle.syntax_diagnostics)},
    )


def _analysis_stage(bundle: AnalysisBundle) -> StageResult:
    if bundle.success and bundle.ast is not None:
        return StageResult(
            stage="Analysis",
            status=StageStatus.PASS,
            summary="Analysis completed without semantic errors.",
        )
    return StageResult(
        stage="Analysis",
        status=StageStatus.FAIL,
        summary="Analysis did not complete successfully.",
    )


def _coverage_stage(bundle: AnalysisBundle) -> StageResult:
    if bundle.coverage is None:
        return StageResult(
            stage="Coverage",
            status=StageStatus.NOT_AVAILABLE,
            summary="Coverage could not be computed.",
        )
    status = bundle.coverage.get("overall_status", "")
    verdict = StageStatus.PASS if status == "COMPLETE" else StageStatus.INCONCLUSIVE
    return StageResult(
        stage="Coverage",
        status=verdict,
        summary=f"Overall coverage {bundle.coverage.get('overall', 0.0):.0%} ({status}).",
        details=bundle.coverage,
    )


def _confidence_stage(bundle: AnalysisBundle) -> StageResult:
    if bundle.confidence is None:
        return StageResult(
            stage="Confidence",
            status=StageStatus.NOT_AVAILABLE,
            summary="Confidence could not be computed.",
        )
    # Confidence is a continuous score, not a pass/fail judgment -- the API
    # reports that it was computed and returns the real score/detail; it
    # does not invent a threshold the domain layer itself does not own.
    return StageResult(
        stage="Confidence",
        status=StageStatus.PASS,
        summary=bundle.confidence.get("detail", "Confidence computed."),
        details=bundle.confidence,
    )


def _java_generation_stage(mb: ModernizationBundle) -> StageResult:
    if mb.project is not None:
        return StageResult(
            stage="Java Generation",
            status=StageStatus.PASS,
            summary=f"{len(mb.project.java_files)} Java file(s) generated.",
            details={"files": sorted(mb.project.java_files.keys())},
        )
    if mb.generation_error:
        return StageResult(
            stage="Java Generation",
            status=StageStatus.FAIL,
            summary=mb.generation_error,
        )
    return StageResult(
        stage="Java Generation",
        status=StageStatus.NOT_AVAILABLE,
        summary=mb.architecture_error or "Java generation did not run.",
    )


def _compilation_stage(mb: ModernizationBundle) -> StageResult:
    if mb.compilation is None:
        return StageResult(
            stage="Compilation",
            status=StageStatus.NOT_AVAILABLE,
            summary=mb.compilation_error or "Compilation did not run.",
        )
    if mb.compilation.success:
        return StageResult(
            stage="Compilation",
            status=StageStatus.PASS,
            summary="Compilation succeeded.",
            details={"jdk_version": mb.compilation.jdk_version},
        )
    return StageResult(
        stage="Compilation",
        status=StageStatus.FAIL,
        summary=f"{len(mb.compilation.errors)} compiler error(s).",
        details={"errors": [e.message for e in mb.compilation.errors]},
    )


def _java_tests_stage(mb: ModernizationBundle) -> StageResult:
    if mb.java_tests is None:
        return StageResult(
            stage="Tests",
            status=StageStatus.NOT_AVAILABLE,
            summary="Java tests did not run (compilation did not succeed).",
        )
    if not mb.java_tests.runs:
        return StageResult(
            stage="Tests",
            status=StageStatus.INCONCLUSIVE,
            summary="No executable behavioral test cases were generated.",
        )
    failed = [
        r.test_id
        for r in mb.java_tests.runs
        if not r.execution_ok or r.assertion_passed is False
    ]
    if failed:
        return StageResult(
            stage="Tests",
            status=StageStatus.FAIL,
            summary=f"{len(failed)} of {len(mb.java_tests.runs)} test(s) failed.",
            details={"failed_test_ids": failed},
        )
    return StageResult(
        stage="Tests",
        status=StageStatus.PASS,
        summary=f"All {len(mb.java_tests.runs)} test(s) passed.",
    )


def _cobol_tests_stage(mb: ModernizationBundle) -> StageResult:
    if mb.behavioral is None:
        return StageResult(
            stage="COBOL Tests",
            status=StageStatus.NOT_AVAILABLE,
            summary=mb.behavioral_error or "Behavioral validation did not run.",
        )
    if mb.behavioral.real_cobol_execution:
        return StageResult(
            stage="COBOL Tests",
            status=StageStatus.PASS,
            summary="Real COBOL execution was used.",
            details={"cobol_runtime": mb.behavioral.cobol_runtime},
        )
    return StageResult(
        stage="COBOL Tests",
        status=StageStatus.NOT_AVAILABLE,
        summary=(
            f"COBOL runtime unavailable ({mb.behavioral.cobol_runtime}); "
            "COBOL source was not executed."
        ),
    )


_BEHAVIORAL_STATUS_MAP = {
    OverallStatus.BEHAVIORALLY_VERIFIED: StageStatus.PASS,
    OverallStatus.BEHAVIORAL_DIFFERENCE_FOUND: StageStatus.FAIL,
    OverallStatus.INCONCLUSIVE: StageStatus.INCONCLUSIVE,
}


def _behavioral_stage(mb: ModernizationBundle) -> StageResult:
    if mb.behavioral is None:
        return StageResult(
            stage="Behavioral Equivalence",
            status=StageStatus.NOT_AVAILABLE,
            summary=mb.behavioral_error or "Behavioral validation did not run.",
        )
    report = mb.behavioral
    return StageResult(
        stage="Behavioral Equivalence",
        status=_BEHAVIORAL_STATUS_MAP[report.overall_status],
        summary=(
            f"PASS: {report.pass_count} / FAIL: {report.fail_count} / "
            f"INCONCLUSIVE: {report.inconclusive_count} (of {report.total_tests})"
        ),
        details={
            "pass_count": report.pass_count,
            "fail_count": report.fail_count,
            "inconclusive_count": report.inconclusive_count,
            "total_tests": report.total_tests,
            "real_cobol_execution": report.real_cobol_execution,
            "real_java_execution": report.real_java_execution,
        },
    )


def _risks_stage(bundle: AnalysisBundle) -> StageResult:
    if bundle.risks is None:
        return StageResult(
            stage="Risks",
            status=StageStatus.NOT_AVAILABLE,
            summary="Modernization risks were not computed.",
        )
    if not bundle.risks:
        return StageResult(
            stage="Risks", status=StageStatus.PASS, summary="No risks identified."
        )
    return StageResult(
        stage="Risks",
        status=StageStatus.INCONCLUSIVE,
        summary=f"{len(bundle.risks)} risk(s) identified -- review recommended.",
        details={"risk_ids": [r.get("risk_id") for r in bundle.risks]},
    )


def _unsupported_syntax_stage(bundle: AnalysisBundle) -> StageResult:
    if bundle.coverage is None:
        return StageResult(
            stage="Unsupported Syntax",
            status=StageStatus.NOT_AVAILABLE,
            summary="Unsupported-syntax coverage was not computed.",
        )
    unsupported = bundle.coverage.get("unsupported_syntax", {})
    occurrences = unsupported.get("total_occurrences", 0)
    if not occurrences:
        return StageResult(
            stage="Unsupported Syntax",
            status=StageStatus.PASS,
            summary="No unsupported or unmodelled syntax.",
        )
    return StageResult(
        stage="Unsupported Syntax",
        status=StageStatus.INCONCLUSIVE,
        summary=f"{occurrences} unsupported/unmodelled occurrence(s).",
        details=unsupported,
    )


def _self_repair_stage() -> StageResult:
    return StageResult(
        stage="Self Repair",
        status=StageStatus.NOT_AVAILABLE,
        summary=_SELF_REPAIR_REASON,
    )


def compute_validation_stages(
    bundle: AnalysisBundle, mb: ModernizationBundle
) -> list[StageResult]:
    return [
        _parser_stage(bundle),
        _analysis_stage(bundle),
        _coverage_stage(bundle),
        _confidence_stage(bundle),
        _java_generation_stage(mb),
        _compilation_stage(mb),
        _java_tests_stage(mb),
        _cobol_tests_stage(mb),
        _behavioral_stage(mb),
        _risks_stage(bundle),
        _unsupported_syntax_stage(bundle),
        _self_repair_stage(),
    ]


def compute_overall_status(stages: list[StageResult]) -> StageStatus:
    """FAIL if any CORE stage FAILed, else INCONCLUSIVE if any core stage
    is INCONCLUSIVE/NOT_AVAILABLE, else PASS. Informational stages
    (Risks, Unsupported Syntax, COBOL Tests, Self Repair) never affect
    this rollup -- see CORE_STAGES."""
    core = [s for s in stages if s.stage in CORE_STAGES]
    if any(s.status is StageStatus.FAIL for s in core):
        return StageStatus.FAIL
    if any(
        s.status in (StageStatus.INCONCLUSIVE, StageStatus.NOT_AVAILABLE) for s in core
    ):
        return StageStatus.INCONCLUSIVE
    return StageStatus.PASS
