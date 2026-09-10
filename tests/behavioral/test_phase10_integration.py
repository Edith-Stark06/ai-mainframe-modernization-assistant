"""
Phase 10 end-to-end (deterministic fixtures):

    COBOL fixture -> analysis -> #129 extraction -> #130 Java test
      -> compile Java -> execute COBOL -> execute Java -> #131 comparison

Proves all three outcomes (PASS / FAIL / INCONCLUSIVE) and one complete
traceability chain: COBOL source -> business rule -> behavioral test ->
Java test -> COBOL execution -> Java execution -> comparison -> status.

Real Java is always used (javac/java are present). Real COBOL is not
available in this environment, so:
  * the "real pipeline" (default executors) integration test asserts
    everything is honestly INCONCLUSIVE — never a fabricated PASS;
  * PASS and FAIL are demonstrated with a deterministic ScriptedExecutor
    standing in for COBOL, exactly as the task requires ("prove the
    comparison logic independently of external runtime availability").
"""

from __future__ import annotations

import json

import pytest

from app.behavioral import (
    ComparisonStatus,
    ExecutionResult,
    OverallStatus,
    ScriptedExecutor,
    extract_behavioral_tests,
    run_behavioral_validation,
)
from app.behavioral.execution.cobol_executor import cobol_runtime_available
from app.java_modernization.compilation import javac_available

pytestmark = pytest.mark.skipif(not javac_available(), reason="javac not on PATH")


def test_real_pipeline_is_honestly_inconclusive_without_a_cobol_runtime(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    assert not cobol_runtime_available(), "test assumes no GnuCOBOL in this environment"
    report = run_behavioral_validation(
        if_else_bundle, if_else_architecture, if_else_project, workspace_root=tmp_path
    )
    assert report.total_tests == 3
    assert report.real_java_execution is True
    assert report.real_cobol_execution is False
    assert report.pass_count == 0 and report.fail_count == 0
    assert report.inconclusive_count == report.total_tests
    assert report.overall_status is OverallStatus.INCONCLUSIVE
    assert any("cobol" in n.lower() for n in report.notes)
    for c in report.comparisons:
        assert "not executed" in c.reason.lower()
        assert c.java_observation.executed is True  # Java genuinely ran


def _scripted_if_else_cobol(matches: bool):
    def script(inputs: dict[str, str]) -> ExecutionResult:
        age = int(inputs.get("AGE", "0"))
        correct = "ADULT" if age > 18 else "MINOR"
        line = correct if matches else "WRONG"
        return ExecutionResult(
            executed=True,
            success=True,
            executor_kind="scripted",
            outputs={"stdout[0]": line},
        )

    return ScriptedExecutor({"IFELSE": script})


def test_scripted_cobol_matching_java_yields_pass(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    report = run_behavioral_validation(
        if_else_bundle,
        if_else_architecture,
        if_else_project,
        workspace_root=tmp_path,
        cobol_executor=_scripted_if_else_cobol(matches=True),
    )
    assert report.pass_count == report.total_tests
    assert report.fail_count == 0 and report.inconclusive_count == 0
    for c in report.comparisons:
        assert c.status is ComparisonStatus.PASS
        assert c.java_observation.executor_kind == "java_real"


def test_scripted_cobol_mismatch_yields_fail(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    report = run_behavioral_validation(
        if_else_bundle,
        if_else_architecture,
        if_else_project,
        workspace_root=tmp_path,
        cobol_executor=_scripted_if_else_cobol(matches=False),
    )
    assert report.fail_count > 0
    assert report.overall_status is OverallStatus.BEHAVIORAL_DIFFERENCE_FOUND
    fails = [c for c in report.comparisons if c.status is ComparisonStatus.FAIL]
    for f in fails:
        assert f.differences
        d = f.differences[0]
        assert d.cobol_value == "WRONG"
        assert d.java_value in ("ADULT", "MINOR")


def test_unsupported_java_candidate_yields_inconclusive_not_fail(
    elig_bundle, elig_architecture, elig_project, tmp_path
):
    # eligibility's generated Java is all BE009 stubs — #129 already knows
    # this, so no execution is even attempted and the result must be
    # INCONCLUSIVE, never a fabricated FAIL or PASS
    report = run_behavioral_validation(
        elig_bundle, elig_architecture, elig_project, workspace_root=tmp_path
    )
    assert report.total_tests == 10
    assert report.pass_count == 0
    assert report.fail_count == 0
    assert report.inconclusive_count == report.total_tests
    assert report.overall_status is OverallStatus.INCONCLUSIVE
    for c in report.comparisons:
        assert c.status is ComparisonStatus.INCONCLUSIVE


def test_report_is_json_serialisable_and_never_hides_inconclusive(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    report = run_behavioral_validation(
        if_else_bundle, if_else_architecture, if_else_project, workspace_root=tmp_path
    )
    d = report.to_dict()
    json.dumps(d)
    assert set(d["counts"]) == {"PASS", "FAIL", "INCONCLUSIVE"}
    assert d["counts"]["INCONCLUSIVE"] == report.total_tests
    # no misleading "equivalence percentage" that excludes inconclusive cases
    assert "equivalence" not in json.dumps(d).lower()


def test_complete_traceability_chain(
    if_else_bundle, if_else_architecture, if_else_project, tmp_path
):
    """COBOL source -> business rule -> behavioral test -> Java test ->
    COBOL execution -> Java execution -> comparison -> PASS/FAIL/INCONCLUSIVE,
    all pointing at the SAME rule/source across every stage."""
    suite = extract_behavioral_tests(if_else_bundle)
    br001_test = next(t for t in suite.tests if "BR-001" in t.business_rule_ids)
    assert br001_test.source_refs[0].source_id == "IFELSE"
    assert br001_test.source_refs[0].paragraph == "MAIN-PARA"

    report = run_behavioral_validation(
        if_else_bundle,
        if_else_architecture,
        if_else_project,
        workspace_root=tmp_path,
        cobol_executor=_scripted_if_else_cobol(matches=True),
    )
    comparison = next(c for c in report.comparisons if c.test_id == br001_test.test_id)
    assert "BR-001" in comparison.business_rule_ids
    assert comparison.source_refs[0].source_id == "IFELSE"
    assert comparison.java_observation.executor_kind == "java_real"
    assert comparison.status is ComparisonStatus.PASS
    assert (
        comparison.artifact_versions.java_project_hash == if_else_project.content_hash()
    )
    assert (
        comparison.artifact_versions.architecture_hash
        == if_else_architecture.content_hash()
    )
    assert comparison.artifact_versions.test_suite_hash == suite.content_hash()
