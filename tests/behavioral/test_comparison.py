"""#131 — execution abstraction + comparison logic (deterministic, scripted)."""

from __future__ import annotations

from app.behavioral.comparison import (
    ArtifactVersions,
    ComparisonStatus,
    compare_observation,
    normalize_line_endings,
    try_parse_exact_integer,
    values_equal,
)
from app.behavioral.execution import ExecutionResult
from app.behavioral.extraction.models import (
    BehavioralTestCase,
    ExpectedBranch,
    ExpectedOutput,
    ExpectedStateChange,
    InputValue,
    InputSource,
)

VERSIONS = ArtifactVersions(
    cobol_source_hash="cobol1",
    java_project_hash="java1",
    architecture_hash="arch1",
    test_suite_hash="suite1",
)


def _test(
    *,
    executable=True,
    reason=None,
    expected_outputs=(),
    expected_state_changes=(),
) -> BehavioralTestCase:
    return BehavioralTestCase(
        test_id="BT-test",
        name="t",
        description="d",
        inputs=(
            InputValue(name="AGE", value="17", source=InputSource.BOUNDARY_GENERATED),
        ),
        expected_branches=(
            ExpectedBranch(
                branch_id="P.IF.true", paragraph="P", condition="X", taken=True
            ),
        ),
        expected_outputs=expected_outputs,
        expected_state_changes=expected_state_changes,
        business_rule_ids=("BR-001",),
        executable=executable,
        inconclusive_reason=reason,
        source_id="SRC",
    )


def _exec(**kw) -> ExecutionResult:
    base = dict(executed=True, success=True, executor_kind="scripted")
    base.update(kw)
    return ExecutionResult(**base)


# --- normalization ------------------------------------------------


def test_numeric_normalization_ignores_leading_zeros_and_sign():
    assert try_parse_exact_integer("018") == 18
    assert try_parse_exact_integer("+18") == 18
    assert try_parse_exact_integer("18.0") is None  # never float-folded
    assert values_equal("018", "18")
    assert not values_equal("18", "19")


def test_string_normalization_only_touches_line_endings_not_padding():
    assert normalize_line_endings("a\r\nb") == "a\nb"
    assert values_equal("line1\r\nline2", "line1\nline2")  # CRLF vs LF only
    assert not values_equal("DENIED ", "DENIED")  # trailing pad NOT stripped
    assert not values_equal("denied", "DENIED")  # case NOT folded


# --- PASS / FAIL / INCONCLUSIVE ------------------------------------


def test_pass_requires_matching_observed_output():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="stdout", kind="display", expected_value="MINOR"),
        )
    )
    cobol = _exec(outputs={"stdout[0]": "MINOR"})
    java = _exec(outputs={"stdout[0]": "MINOR"})
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.PASS
    assert c.differences == ()


def test_fail_on_observed_output_mismatch():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="stdout", kind="display", expected_value="MINOR"),
        )
    )
    cobol = _exec(outputs={"stdout[0]": "DENIED"})
    java = _exec(outputs={"stdout[0]": "APPROVED"})
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.FAIL
    assert c.differences[0].cobol_value == "DENIED"
    assert c.differences[0].java_value == "APPROVED"


def test_fail_on_calculation_mismatch():
    test = _test(
        expected_state_changes=(
            ExpectedStateChange(field="COUNTER", from_value="1", to_value="2"),
        )
    )
    cobol = _exec(state_changes={"COUNTER": "2"})
    java = _exec(state_changes={"COUNTER": "3"})
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.FAIL
    assert c.differences[0].field == "COUNTER"


def test_fail_on_status_mismatch():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="WS-RESULT", kind="field", expected_value="DENIED"),
        )
    )
    cobol = _exec(outputs={"WS-RESULT": "DENIED"})
    java = _exec(outputs={"WS-RESULT": "ELIGIBLE"})
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.FAIL


def test_inconclusive_when_cobol_not_executed():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="stdout", kind="display", expected_value="X"),
        )
    )
    cobol = ExecutionResult(
        executed=False,
        success=False,
        executor_kind="cobol_unavailable",
        diagnostics=("no cobc",),
    )
    java = _exec(outputs={"stdout[0]": "X"})
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.INCONCLUSIVE
    assert "not executed" in c.reason.lower()


def test_inconclusive_when_marked_non_executable_by_129():
    test = _test(executable=False, reason="generator stub BE009")
    unattempted = ExecutionResult(
        executed=False, success=False, executor_kind="not_attempted"
    )
    c = compare_observation(test, unattempted, unattempted, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.INCONCLUSIVE
    assert c.reason == "generator stub BE009"


def test_inconclusive_on_missing_observation():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="WS-RESULT", kind="field", expected_value="DENIED"),
        )
    )
    cobol = _exec(outputs={})  # field never observed
    java = _exec(outputs={"WS-RESULT": "DENIED"})
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.INCONCLUSIVE
    assert "not available" in c.reason


def test_inconclusive_when_java_failed_before_reaching_behavior():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="stdout", kind="display", expected_value="X"),
        )
    )
    cobol = _exec(outputs={"stdout[0]": "X"})
    java = _exec(success=False, diagnostics=("threw NPE",))
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.INCONCLUSIVE
    assert "java failed" in c.reason.lower()


def test_inconclusive_when_nothing_was_observable_to_compare():
    test = _test()  # no expected_outputs, no expected_state_changes at all
    cobol = _exec()
    java = _exec()
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.status is ComparisonStatus.INCONCLUSIVE


# --- traceability + versioning -------------------------------------


def test_comparison_preserves_source_and_rule_traceability():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="stdout", kind="display", expected_value="X"),
        )
    )
    cobol = _exec(outputs={"stdout[0]": "X"})
    java = _exec(outputs={"stdout[0]": "X"})
    c = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert c.business_rule_ids == ("BR-001",)
    assert c.artifact_versions == VERSIONS


def test_comparison_id_is_deterministic_and_version_sensitive():
    test = _test(
        expected_outputs=(
            ExpectedOutput(name="stdout", kind="display", expected_value="X"),
        )
    )
    cobol = _exec(outputs={"stdout[0]": "X"})
    java = _exec(outputs={"stdout[0]": "X"})
    a = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    b = compare_observation(test, cobol, java, artifact_versions=VERSIONS)
    assert a.comparison_id == b.comparison_id
    other_versions = VERSIONS.model_copy(update={"java_project_hash": "java2"})
    c = compare_observation(test, cobol, java, artifact_versions=other_versions)
    assert c.comparison_id != a.comparison_id
