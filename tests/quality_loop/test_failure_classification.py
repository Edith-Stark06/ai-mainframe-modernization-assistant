"""Phase 11 — normalizing raw pipeline outputs into FailureRecord."""

from __future__ import annotations

from app.behavioral.comparison.models import (
    ArtifactVersions,
    BehavioralComparison,
    ComparisonStatus,
    Difference,
    OverallStatus,
    Phase10Report,
)
from app.behavioral.execution.models import ExecutionResult
from app.behavioral.javatests.models import (
    JavaTarget,
    JavaTestArtifact,
    JavaTestRun,
    JavaTestSuiteResult,
)
from app.java_modernization.architecture.models import SourceRef
from app.java_modernization.compilation.models import (
    CompilationResult,
    CompilerDiagnostic,
    DiagnosticSeverity,
)
from app.quality_loop.eligibility import repair_eligibility
from app.quality_loop.failure import (
    FailureCategory,
    classify_failures,
    group_failures,
    prioritize,
)

_SM = SourceRef(
    source_id="S1",
    source_path="S1.cbl",
    line_start=10,
    line_end=12,
    paragraph="CHECK-ELIG",
)
_AV = ArtifactVersions(
    cobol_source_hash="c",
    java_project_hash="j",
    architecture_hash="a",
    test_suite_hash="t",
)


def _exec(**kw):
    base = dict(executed=True, success=True, executor_kind="scripted")
    base.update(kw)
    return ExecutionResult(**base)


class TestCompilationErrorClassification:
    def test_error_diagnostic_becomes_compilation_error(self):
        comp = CompilationResult(
            success=False,
            diagnostics=(
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="';' expected",
                    file="src/Foo.java",
                    line=12,
                    cobol_source_mapping=_SM,
                    business_rule_ids=("BR-1",),
                ),
            ),
        )
        failures = classify_failures(compilation=comp)
        assert len(failures) == 1
        assert failures[0].category is FailureCategory.COMPILATION_ERROR
        assert failures[0].affected_artifact == "src/Foo.java"
        assert failures[0].source_mapping == _SM

    def test_warnings_are_not_failures(self):
        comp = CompilationResult(
            success=True,
            diagnostics=(
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    message="unchecked",
                    file="F.java",
                ),
            ),
        )
        assert classify_failures(compilation=comp) == ()

    def test_missing_source_mapping_downgrades_to_provenance_failure(self):
        comp = CompilationResult(
            success=False,
            diagnostics=(
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="cannot find symbol",
                    file="src/Foo.java",
                    line=3,
                    cobol_source_mapping=None,
                ),
            ),
        )
        failures = classify_failures(compilation=comp)
        assert len(failures) == 1
        assert failures[0].category is FailureCategory.PROVENANCE_FAILURE


class TestJavaTestClassification:
    def test_execution_failure_distinct_from_assertion_failure(self):
        art = JavaTestArtifact(
            test_id="BT-1",
            behavioral_test_id="BT-1",
            file_path="src/FooBehaviorHarness.java",
            test_name="t1",
            java_target=JavaTarget(java_class="Foo", java_method="run"),
            run_args=(),
            source_refs=(_SM,),
        )
        result = JavaTestSuiteResult(
            source_id="S1",
            compiled=True,
            artifacts=(art,),
            runs=(
                JavaTestRun(test_id="BT-1", execution_ok=False, diagnostics=("crash",)),
            ),
        )
        failures = classify_failures(java_tests=result)
        assert len(failures) == 1
        assert failures[0].category is FailureCategory.EXECUTION_FAILURE

    def test_assertion_failure_is_test_failure(self):
        art = JavaTestArtifact(
            test_id="BT-2",
            behavioral_test_id="BT-2",
            file_path="src/FooBehaviorHarness.java",
            test_name="t2",
            java_target=JavaTarget(java_class="Foo", java_method="run"),
            run_args=(),
            source_refs=(_SM,),
        )
        result = JavaTestSuiteResult(
            source_id="S1",
            compiled=True,
            artifacts=(art,),
            runs=(
                JavaTestRun(
                    test_id="BT-2",
                    execution_ok=True,
                    assertion_passed=False,
                    failed_fields=("wsResult",),
                ),
            ),
        )
        failures = classify_failures(java_tests=result)
        assert len(failures) == 1
        assert failures[0].category is FailureCategory.TEST_FAILURE

    def test_harness_compile_failure_is_surfaced_as_compilation_error(self):
        result = JavaTestSuiteResult(
            source_id="S1", compiled=False, compile_diagnostics=("boom",)
        )
        failures = classify_failures(java_tests=result)
        assert len(failures) == 1
        # no source mapping is available for a harness-level compile failure,
        # so it is downgraded to PROVENANCE_FAILURE (never speculatively repaired)
        assert failures[0].category is FailureCategory.PROVENANCE_FAILURE

    def test_passing_run_produces_no_failure(self):
        art = JavaTestArtifact(
            test_id="BT-3",
            behavioral_test_id="BT-3",
            file_path="src/F.java",
            test_name="t3",
            java_target=JavaTarget(java_class="Foo", java_method="run"),
            run_args=(),
        )
        result = JavaTestSuiteResult(
            source_id="S1",
            compiled=True,
            artifacts=(art,),
            runs=(
                JavaTestRun(test_id="BT-3", execution_ok=True, assertion_passed=True),
            ),
        )
        assert classify_failures(java_tests=result) == ()


class TestBehavioralClassification:
    def _comparison(self, status, reason="", differences=(), source_refs=()):
        return BehavioralComparison(
            comparison_id=f"cmp-{status.value}-{reason[:8]}",
            test_id="BT-9",
            status=status,
            cobol_observation=_exec(),
            java_observation=_exec(),
            differences=differences,
            source_refs=source_refs,
            reason=reason,
            artifact_versions=_AV,
        )

    def test_fail_with_difference_is_behavioral_mismatch(self):
        diff = Difference(
            field="wsResult",
            cobol_value="DENIED",
            java_value="APPROVED",
            expected_behavior="match COBOL",
            source_ref=_SM,
            business_rule_id="BR-1",
        )
        report = Phase10Report(
            source_id="S1",
            overall_status=OverallStatus.BEHAVIORAL_DIFFERENCE_FOUND,
            comparisons=(self._comparison(ComparisonStatus.FAIL, differences=(diff,)),),
        )
        failures = classify_failures(behavioral=report)
        assert len(failures) == 1
        assert failures[0].category is FailureCategory.BEHAVIORAL_MISMATCH
        assert failures[0].source_mapping == _SM

    def test_inconclusive_unsupported_marker(self):
        report = Phase10Report(
            source_id="S1",
            overall_status=OverallStatus.INCONCLUSIVE,
            comparisons=(
                self._comparison(
                    ComparisonStatus.INCONCLUSIVE,
                    reason="marked non-executable (BE009)",
                    source_refs=(_SM,),
                ),
            ),
        )
        failures = classify_failures(behavioral=report)
        assert failures[0].category is FailureCategory.UNSUPPORTED_BEHAVIOR

    def test_inconclusive_infrastructure_marker(self):
        report = Phase10Report(
            source_id="S1",
            overall_status=OverallStatus.INCONCLUSIVE,
            comparisons=(
                self._comparison(
                    ComparisonStatus.INCONCLUSIVE,
                    reason="COBOL side not executed — runtime unavailable",
                    source_refs=(_SM,),
                ),
            ),
        )
        failures = classify_failures(behavioral=report)
        assert failures[0].category is FailureCategory.INFRASTRUCTURE_FAILURE

    def test_inconclusive_no_source_refs_is_provenance_failure(self):
        report = Phase10Report(
            source_id="S1",
            overall_status=OverallStatus.INCONCLUSIVE,
            comparisons=(
                self._comparison(
                    ComparisonStatus.INCONCLUSIVE, reason="no mapping", source_refs=()
                ),
            ),
        )
        failures = classify_failures(behavioral=report)
        assert failures[0].category is FailureCategory.PROVENANCE_FAILURE

    def test_pass_produces_no_failure(self):
        report = Phase10Report(
            source_id="S1",
            overall_status=OverallStatus.BEHAVIORALLY_VERIFIED,
            comparisons=(self._comparison(ComparisonStatus.PASS),),
        )
        assert classify_failures(behavioral=report) == ()


class TestPriorityAndGrouping:
    def test_priority_order_is_deterministic_and_documented(self):
        comp = CompilationResult(
            success=False,
            diagnostics=(
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="e",
                    file="F.java",
                    line=1,
                    cobol_source_mapping=_SM,
                ),
            ),
        )
        diff = Difference(
            field="x",
            cobol_value="1",
            java_value="2",
            expected_behavior="match",
            source_ref=_SM,
        )
        report = Phase10Report(
            source_id="S1",
            overall_status=OverallStatus.BEHAVIORAL_DIFFERENCE_FOUND,
            comparisons=(
                BehavioralComparison(
                    comparison_id="c1",
                    test_id="t1",
                    status=ComparisonStatus.FAIL,
                    cobol_observation=_exec(),
                    java_observation=_exec(),
                    differences=(diff,),
                    artifact_versions=_AV,
                ),
            ),
        )
        failures = classify_failures(compilation=comp, behavioral=report)
        # compilation errors always outrank behavioral mismatches
        assert failures[0].category is FailureCategory.COMPILATION_ERROR
        assert failures[1].category is FailureCategory.BEHAVIORAL_MISMATCH

    def test_prioritize_never_depends_on_input_order(self):
        comp = CompilationResult(
            success=False,
            diagnostics=(
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="e",
                    file="F.java",
                    line=1,
                    cobol_source_mapping=_SM,
                ),
            ),
        )
        forward = classify_failures(compilation=comp)
        backward = tuple(reversed(prioritize(list(forward))))
        assert tuple(prioritize(list(backward))) == forward

    def test_group_failures_groups_by_affected_artifact(self):
        comp = CompilationResult(
            success=False,
            diagnostics=(
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="e1",
                    file="A.java",
                    line=1,
                    cobol_source_mapping=_SM,
                ),
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="e2",
                    file="A.java",
                    line=2,
                    cobol_source_mapping=_SM,
                ),
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="e3",
                    file="B.java",
                    line=1,
                    cobol_source_mapping=_SM,
                ),
            ),
        )
        failures = classify_failures(compilation=comp)
        groups = group_failures(failures)
        assert len(groups) == 2
        assert {f.affected_artifact for f in groups[0]} == {"A.java"}
        assert {f.affected_artifact for f in groups[1]} == {"B.java"}


class TestEligibilityIntegration:
    def test_never_auto_repaired_categories_are_never_eligible(self):
        report = Phase10Report(
            source_id="S1",
            overall_status=OverallStatus.INCONCLUSIVE,
            comparisons=(
                BehavioralComparison(
                    comparison_id="c1",
                    test_id="t1",
                    status=ComparisonStatus.INCONCLUSIVE,
                    cobol_observation=_exec(),
                    java_observation=_exec(),
                    reason="marked non-executable",
                    source_refs=(_SM,),
                    artifact_versions=_AV,
                ),
            ),
        )
        failures = classify_failures(behavioral=report)
        assert failures[0].category is FailureCategory.UNSUPPORTED_BEHAVIOR
        ok, reason = repair_eligibility(failures[0])
        assert ok is False
        assert "never auto-repaired" in reason

    def test_compilation_error_with_full_evidence_is_eligible(self):
        comp = CompilationResult(
            success=False,
            diagnostics=(
                CompilerDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="e",
                    file="F.java",
                    line=1,
                    cobol_source_mapping=_SM,
                ),
            ),
        )
        failures = classify_failures(compilation=comp)
        ok, _ = repair_eligibility(failures[0])
        assert ok is True
