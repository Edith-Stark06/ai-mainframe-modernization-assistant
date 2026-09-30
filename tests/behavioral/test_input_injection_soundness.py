"""
Input injection soundness for behavioral tests (follow-up to ``ACCEPT``).

Purpose:
    The Java harness presets each input field and then runs the whole program.
    Once ``ACCEPT`` and multi-statement programs translate, that exposed three
    ways a generated test could fail for a reason that has nothing to do with
    the translation:

    1. the program ``ACCEPT``s the injected field, replacing the preset;
    2. the program assigns the injected field earlier in the same paragraph
       as the condition under test (``COMPUTE X = ...`` then ``IF X > n``);
    3. the harness could not preset a ``double`` field, and compared numbers
       as strings (``"50000.0"`` != ``"50000"``).

    (1) and (2) are now recorded as non-executable tests with a stated reason
    instead of false FAILs; (3) is fixed in the harness. A real subprocess is
    also never left waiting on the parent's stdin.

Coverage:
    Extractor -- ACCEPT'd input and same-paragraph-assigned input downgraded,
                 a genuinely independent input left executable.
    Harness   -- double field preset + numeric-aware comparison, end to end.
    Runners   -- subprocess is started with an empty stdin.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from app.behavioral.extraction import extract_behavioral_tests
from app.behavioral.javatests import JavaTestRunner
from app.dataset.analysis_bundle import build_analysis_bundle
from app.java_modernization.architecture import build_architecture
from app.java_modernization.compilation import javac_available
from app.java_modernization.generation import generate_project

_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INJECT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-TYPED   PIC 9(3).
       01  WS-BASE    PIC 9(5)V99.
       01  WS-TOTAL   PIC 9(5)V99.
       01  WS-FREE    PIC 9(3).
       01  WS-FLAG    PIC X(10).
       PROCEDURE DIVISION.
       MAIN-PARA.
           ACCEPT WS-TYPED.
           PERFORM CHECK-TYPED.
           PERFORM CHECK-TOTAL.
           PERFORM CHECK-FREE.
           STOP RUN.
       CHECK-TYPED.
           IF WS-TYPED > 5
               MOVE 'BIG' TO WS-FLAG
           ELSE
               MOVE 'SMALL' TO WS-FLAG
           END-IF.
       CHECK-TOTAL.
           COMPUTE WS-TOTAL = WS-BASE * 2.
           IF WS-TOTAL > 100
               MOVE 'HIGH' TO WS-FLAG
           ELSE
               MOVE 'LOW' TO WS-FLAG
           END-IF.
       CHECK-FREE.
           IF WS-FREE > 10
               MOVE 'FREE-HIGH' TO WS-FLAG
           ELSE
               MOVE 'FREE-LOW' TO WS-FLAG
           END-IF.
"""


@pytest.fixture(scope="module")
def bundle():
    return build_analysis_bundle("INJECT", _SOURCE, tempfile.mkdtemp())


def _tests_for(suite, variable: str):
    return [t for t in suite.tests if any(i.name == variable for i in t.inputs)]


def test_accepted_input_is_not_executable(bundle) -> None:
    tests = _tests_for(extract_behavioral_tests(bundle), "WS-TYPED")
    assert tests
    for t in tests:
        assert not t.executable
        assert t.inconclusive_reason and "ACCEPT" in t.inconclusive_reason


def test_input_assigned_earlier_in_the_paragraph_is_not_executable(bundle) -> None:
    tests = _tests_for(extract_behavioral_tests(bundle), "WS-TOTAL")
    assert tests
    for t in tests:
        assert not t.executable
        assert t.inconclusive_reason
        assert "assigned earlier in paragraph CHECK-TOTAL" in t.inconclusive_reason


def test_independent_input_stays_executable(bundle) -> None:
    tests = _tests_for(extract_behavioral_tests(bundle), "WS-FREE")
    assert tests
    assert all(t.executable for t in tests)


def test_assignment_in_another_paragraph_does_not_downgrade(bundle) -> None:
    # WS-FLAG is MOVEd everywhere but is never an *input* of a condition here;
    # the point is the narrow rule: only same-paragraph-before and ACCEPT count.
    suite = extract_behavioral_tests(bundle)
    assert any(t.executable for t in suite.tests)


# ---------------------------------------------------------------------------
# Harness: double presets and numeric-aware comparison, end to end
# ---------------------------------------------------------------------------

_DOUBLE_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DBLTEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-AMOUNT PIC 9(5)V99.
       01  WS-STATUS PIC X(10).
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM CHECK-AMOUNT.
           STOP RUN.
       CHECK-AMOUNT.
           IF WS-AMOUNT >= 500
               MOVE 'HIGH' TO WS-STATUS
           ELSE
               MOVE 'LOW' TO WS-STATUS
           END-IF.
"""


@pytest.mark.skipif(not javac_available(), reason="javac not on PATH")
def test_double_field_is_preset_and_compared_by_value(tmp_path: Path) -> None:
    bundle = build_analysis_bundle("DBLTEST", _DOUBLE_SOURCE, tempfile.mkdtemp())
    project = generate_project(bundle, build_architecture(bundle))
    suite = extract_behavioral_tests(bundle)
    assert suite.executable_tests

    result = JavaTestRunner(tmp_path).run_suite(suite, project)
    assert result.compiled
    assert result.runs
    for run in result.runs:
        assert run.execution_ok, run.diagnostics
        assert run.assertion_passed is True, run.stdout


@pytest.mark.skipif(not javac_available(), reason="javac not on PATH")
def test_double_field_value_matches_its_integer_spelling(tmp_path: Path) -> None:
    """``500`` (as COBOL writes it) must equal the Java double ``500.0``."""
    from app.behavioral.javatests import generate_java_tests

    bundle = build_analysis_bundle("DBLTEST", _DOUBLE_SOURCE, tempfile.mkdtemp())
    project = generate_project(bundle, build_architecture(bundle))
    files, artifacts = generate_java_tests(extract_behavioral_tests(bundle), project)
    artifact = artifacts[0].model_copy(
        update={"run_args": ("wsAmount=500", "expect:wsAmount=500")}
    )
    runner = JavaTestRunner(tmp_path)
    compiled = runner._compiler.compile(  # noqa: SLF001
        project.model_copy(update={"files": {**project.files, **files}})
    )
    assert compiled.success
    run = runner._run_one(  # noqa: SLF001
        artifact, Path(compiled.workspace) / "out", project.main_class
    )
    assert run.execution_ok, run.diagnostics
    assert run.assertion_passed is True, run.stdout
    assert run.field_values.get("wsAmount") == "500.0"


@pytest.mark.skipif(not javac_available(), reason="javac not on PATH")
def test_harness_source_compares_numbers_by_value() -> None:
    from app.behavioral.javatests.generator import render_harness

    source = render_harness("Anything")
    assert "f.setDouble(" in source
    assert "BigDecimal" in source


# ---------------------------------------------------------------------------
# Runners never inherit the parent's stdin
# ---------------------------------------------------------------------------


def test_java_test_runner_starts_java_with_empty_stdin(tmp_path: Path) -> None:
    from app.behavioral.javatests.models import JavaTarget, JavaTestArtifact

    artifact = JavaTestArtifact(
        test_id="T",
        behavioral_test_id="T",
        file_path="src/XBehaviorHarness.java",
        test_name="t",
        java_target=JavaTarget(java_class="X", java_method="run"),
        run_args=(),
        source_refs=(),
        business_rule_ids=(),
        assumptions=(),
    )
    completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    with mock.patch(
        "app.behavioral.javatests.runner.subprocess.run", return_value=completed
    ) as run:
        JavaTestRunner(tmp_path)._run_one(artifact, tmp_path, "X")  # noqa: SLF001
    assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL
