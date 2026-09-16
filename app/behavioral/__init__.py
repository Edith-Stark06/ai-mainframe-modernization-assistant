"""
Phase 10 — behavioral equivalence (#129-#131).

    AnalysisBundle
      -> #129 extract_behavioral_tests()   deterministic, language-independent
      -> #130 generate_java_tests() / JavaTestRunner   compile + execute real Java
      -> #131 ProgramExecutor (COBOL / Java / scripted) + compare_observation()
      -> Phase10Report   PASS / FAIL / INCONCLUSIVE — never inferred, only observed

Central rule: PASS requires BOTH sides to have actually executed and
every required observation to have matched. A compiling Java program, a
passing generated Java self-test, or matching static analysis are never
sufficient on their own — see :mod:`app.behavioral.comparison.comparator`.
"""

from __future__ import annotations

from app.behavioral.comparison import (
    ArtifactVersions,
    BehavioralComparison,
    ComparisonStatus,
    Difference,
    OverallStatus,
    Phase10Report,
    aggregate_report,
    compare_observation,
)
from app.behavioral.execution import (
    CobolExecutor,
    ExecutionResult,
    JavaExecutor,
    ProgramExecutor,
    ProgramSpec,
    ScriptedExecutor,
    cobol_runtime_available,
    java_runtime_available,
)
from app.behavioral.extraction import (
    BehavioralSuite,
    BehavioralTestCase,
    extract_behavioral_tests,
)
from app.behavioral.javatests import JavaTestRunner, java_available
from app.behavioral.orchestrator import run_behavioral_validation

__all__ = [
    "extract_behavioral_tests",
    "BehavioralSuite",
    "BehavioralTestCase",
    "JavaTestRunner",
    "java_available",
    "ProgramExecutor",
    "ProgramSpec",
    "ExecutionResult",
    "CobolExecutor",
    "cobol_runtime_available",
    "JavaExecutor",
    "java_runtime_available",
    "ScriptedExecutor",
    "compare_observation",
    "aggregate_report",
    "ArtifactVersions",
    "BehavioralComparison",
    "ComparisonStatus",
    "Difference",
    "OverallStatus",
    "Phase10Report",
    "run_behavioral_validation",
]
