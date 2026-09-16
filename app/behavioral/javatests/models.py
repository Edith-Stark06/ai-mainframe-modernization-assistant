"""#130 — generated Java test artifact + execution result models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.java_modernization.architecture.models import SourceRef
from app.behavioral.version import JAVA_TEST_VERSION

__all__ = ["JavaTarget", "JavaTestArtifact", "JavaTestRun", "JavaTestSuiteResult"]


class JavaTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    java_class: str
    java_method: str


class JavaTestArtifact(BaseModel):
    """A behavioral test case bound to a runnable harness invocation.

    No JUnit (or any framework) is present in this repository, and the
    behavior under test is a single reflective call — a tiny, deterministic,
    framework-free harness (one file per source, ``<Main>BehaviorHarness.java``)
    is the smallest mechanism that can compile + execute + self-assert.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_id: str
    behavioral_test_id: str
    file_path: str
    test_name: str
    java_target: JavaTarget
    run_args: tuple[str, ...]
    source_refs: tuple[SourceRef, ...] = ()
    business_rule_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    java_test_version: str = JAVA_TEST_VERSION

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class JavaTestRun(BaseModel):
    """The result of actually compiling + executing one :class:`JavaTestArtifact`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_id: str
    #: the harness process started and ran to completion (no crash/timeout);
    #: distinct from whether its self-assertion passed
    execution_ok: bool
    assertion_passed: bool | None = None
    failed_fields: tuple[str, ...] = ()
    stdout_lines: tuple[str, ...] = ()
    field_values: dict[str, str] = Field(default_factory=dict)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    timed_out: bool = False
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class JavaTestSuiteResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    compiled: bool
    compile_diagnostics: tuple[str, ...] = ()
    artifacts: tuple[JavaTestArtifact, ...] = ()
    runs: tuple[JavaTestRun, ...] = ()

    def run_by_test_id(self) -> dict[str, JavaTestRun]:
        return {r.test_id: r for r in self.runs}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "compiled": self.compiled,
            "compile_diagnostics": list(self.compile_diagnostics),
            "artifact_count": len(self.artifacts),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "runs": [r.to_dict() for r in self.runs],
        }
