"""#130 — Java test generation, compilation, execution, assertions."""

from __future__ import annotations

import pytest

from app.behavioral.extraction import extract_behavioral_tests
from app.behavioral.javatests import (
    HARNESS_SUFFIX,
    JavaTestRunner,
    generate_java_tests,
    java_available,
)
from app.java_modernization.compilation import javac_available

pytestmark = pytest.mark.skipif(not javac_available(), reason="javac not on PATH")


def test_harness_generation_produces_one_artifact_per_executable_test(
    if_else_bundle, if_else_project
):
    suite = extract_behavioral_tests(if_else_bundle)
    files, artifacts = generate_java_tests(suite, if_else_project)
    harness_path = f"src/{if_else_project.main_class}{HARNESS_SUFFIX}.java"
    assert harness_path in files
    assert len(artifacts) == len(suite.executable_tests)


def test_compilation_succeeds(combined_bundle, combined_project, tmp_path):
    suite = extract_behavioral_tests(combined_bundle)
    result = JavaTestRunner(tmp_path).run_suite(suite, combined_project)
    assert result.compiled
    assert not result.compile_diagnostics


def test_successful_execution_and_self_assertion(
    combined_bundle, combined_project, tmp_path
):
    suite = extract_behavioral_tests(combined_bundle)
    result = JavaTestRunner(tmp_path).run_suite(suite, combined_project)
    assert result.runs
    for run in result.runs:
        assert run.execution_ok
        assert run.assertion_passed is True
        # field_values is keyed by the JAVA field name (this is the raw
        # Java-side self-check; #131's ExecutionResult normalizes back to
        # the COBOL field name for cross-language comparison)
        assert run.field_values.get("counter") is not None


def test_failing_assertion_is_reported_not_masked(
    combined_bundle, combined_project, tmp_path
):
    # ask the harness to expect a WRONG value -> assertion must fail, not
    # silently pass or crash
    suite = extract_behavioral_tests(combined_bundle)
    files, artifacts = generate_java_tests(suite, combined_project)
    bad_artifact = artifacts[0].model_copy(
        update={
            "run_args": tuple(
                a if not a.startswith("expect:counter=") else "expect:counter=999"
                for a in artifacts[0].run_args
            )
        }
    )
    runner = JavaTestRunner(tmp_path)
    test_project = combined_project.model_copy(
        update={"files": {**combined_project.files, **files}}
    )
    compilation = runner._compiler.compile(test_project)  # noqa: SLF001
    assert compilation.success
    from pathlib import Path

    out_dir = Path(compilation.workspace) / "out"
    run = runner._run_one(
        bad_artifact, out_dir, combined_project.main_class
    )  # noqa: SLF001
    assert run.execution_ok  # the program itself ran fine
    assert run.assertion_passed is False
    assert "counter" in run.failed_fields


def test_error_expectation_field_is_readable(elig_bundle, elig_project, tmp_path):
    # eligibility's rules are all non-executable (BE009 stubs / unreached),
    # so #130 must generate ZERO artifacts for it — not fabricate a test
    suite = extract_behavioral_tests(elig_bundle)
    files, artifacts = generate_java_tests(suite, elig_project)
    assert artifacts == ()


def test_source_and_business_rule_mapping_on_artifacts(if_else_bundle, if_else_project):
    suite = extract_behavioral_tests(if_else_bundle)
    _, artifacts = generate_java_tests(suite, if_else_project)
    for a in artifacts:
        assert a.source_refs
        assert a.business_rule_ids
        assert a.java_target.java_class == if_else_project.main_class
        assert a.assumptions


def test_deterministic_harness_and_artifact_ids(if_else_bundle, if_else_project):
    suite = extract_behavioral_tests(if_else_bundle)
    files1, arts1 = generate_java_tests(suite, if_else_project)
    files2, arts2 = generate_java_tests(suite, if_else_project)
    assert files1 == files2
    assert [a.test_id for a in arts1] == [a.test_id for a in arts2]
    assert [a.run_args for a in arts1] == [a.run_args for a in arts2]


def test_malformed_generated_project_is_a_structured_compile_failure(
    if_else_bundle, if_else_project, tmp_path
):
    suite = extract_behavioral_tests(if_else_bundle)
    broken = if_else_project.model_copy(
        update={
            "files": {
                **if_else_project.files,
                f"src/{if_else_project.main_class}.java": "this is not java",
            }
        }
    )
    result = JavaTestRunner(tmp_path).run_suite(suite, broken)
    assert not result.compiled
    assert result.compile_diagnostics
    assert result.runs == ()


def test_java_available_reports_toolchain_presence():
    assert java_available() is javac_available()
