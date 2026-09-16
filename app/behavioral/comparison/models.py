"""#131 — the behavioral comparison result + Phase 10 aggregate report."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.behavioral.execution.models import ExecutionResult
from app.behavioral.version import COMPARISON_VERSION
from app.java_modernization.architecture.models import SourceRef

__all__ = [
    "ComparisonStatus",
    "Difference",
    "ArtifactVersions",
    "BehavioralComparison",
    "OverallStatus",
    "Phase10Report",
]


class ComparisonStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class OverallStatus(str, Enum):
    BEHAVIORALLY_VERIFIED = "BEHAVIORALLY_VERIFIED"
    BEHAVIORAL_DIFFERENCE_FOUND = "BEHAVIORAL_DIFFERENCE_FOUND"
    INCONCLUSIVE = "INCONCLUSIVE"


class Difference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    cobol_value: str | None
    java_value: str | None
    expected_behavior: str
    source_ref: SourceRef | None = None
    business_rule_id: str | None = None
    severity: str = "behavioral"


class ArtifactVersions(BaseModel):
    """Exactly which generated artifacts this comparison was computed from.

    Prevents comparing results from two different generated versions —
    a stale Java project against a re-extracted test suite, etc.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cobol_source_hash: str
    java_project_hash: str
    architecture_hash: str
    test_suite_hash: str


class BehavioralComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    comparison_id: str
    test_id: str
    comparison_version: str = COMPARISON_VERSION

    status: ComparisonStatus
    cobol_observation: ExecutionResult
    java_observation: ExecutionResult

    differences: tuple[Difference, ...] = ()

    source_refs: tuple[SourceRef, ...] = ()
    business_rule_ids: tuple[str, ...] = ()

    confidence: str = "high"
    reason: str = ""

    artifact_versions: ArtifactVersions

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class Phase10Report(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    overall_status: OverallStatus
    comparisons: tuple[BehavioralComparison, ...] = ()

    total_tests: int = 0
    executable_tests: int = 0
    non_executable_tests: int = 0
    cobol_execution_successes: int = 0
    java_execution_successes: int = 0

    pass_count: int = 0
    fail_count: int = 0
    inconclusive_count: int = 0

    real_cobol_execution: bool = False
    real_java_execution: bool = False
    cobol_runtime: str = "unavailable"

    notes: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def pass_rate(self) -> float:
        return round(self.pass_count / self.total_tests, 4) if self.total_tests else 0.0

    @property
    def fail_rate(self) -> float:
        return round(self.fail_count / self.total_tests, 4) if self.total_tests else 0.0

    @property
    def inconclusive_rate(self) -> float:
        return (
            round(self.inconclusive_count / self.total_tests, 4)
            if self.total_tests
            else 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "overall_status": self.overall_status.value,
            "real_cobol_execution": self.real_cobol_execution,
            "real_java_execution": self.real_java_execution,
            "cobol_runtime": self.cobol_runtime,
            "total_tests": self.total_tests,
            "executable_tests": self.executable_tests,
            "non_executable_tests": self.non_executable_tests,
            "cobol_execution_successes": self.cobol_execution_successes,
            "java_execution_successes": self.java_execution_successes,
            "counts": {
                "PASS": self.pass_count,
                "FAIL": self.fail_count,
                "INCONCLUSIVE": self.inconclusive_count,
            },
            "rates": {
                "pass_rate": self.pass_rate,
                "fail_rate": self.fail_rate,
                "inconclusive_rate": self.inconclusive_rate,
            },
            "notes": list(self.notes),
            "comparisons": [c.to_dict() for c in self.comparisons],
        }
