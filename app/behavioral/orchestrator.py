"""
Phase 10 orchestrator (#129 -> #130 -> #131).

    AnalysisBundle
      -> extract_behavioral_tests()      (#129, deterministic)
      -> [compile + run the #130 harness feeds JavaExecutor observations]
      -> ProgramExecutor.execute() x2    (#131: COBOL side + Java side)
      -> compare_observation()           (#131)
      -> aggregate_report()

Defaults to the REAL executors (:class:`CobolExecutor`, :class:`JavaExecutor`).
If GnuCOBOL is unavailable — the default in this environment — every
comparison degrades to INCONCLUSIVE, never PASS/FAIL, and the report says
so explicitly (``real_cobol_execution=False``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.behavioral.comparison.comparator import compare_observation
from app.behavioral.comparison.models import ArtifactVersions, Phase10Report
from app.behavioral.comparison.report import aggregate_report
from app.behavioral.execution.base import ProgramExecutor
from app.behavioral.execution.cobol_executor import (
    CobolExecutor,
    cobol_compiler_version,
    cobol_runtime_available,
)
from app.behavioral.execution.java_executor import JavaExecutor, java_runtime_available
from app.behavioral.execution.models import ExecutionResult, ProgramSpec
from app.behavioral.extraction.extractor import extract_behavioral_tests
from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.architecture.models import JavaArchitecture
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["run_behavioral_validation"]


def _source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def run_behavioral_validation(
    bundle: AnalysisBundle,
    architecture: JavaArchitecture,
    project: GeneratedProject,
    *,
    workspace_root: str | Path,
    cobol_executor: ProgramExecutor | None = None,
    java_executor: ProgramExecutor | None = None,
) -> Phase10Report:
    suite = extract_behavioral_tests(bundle)
    versions = ArtifactVersions(
        cobol_source_hash=_source_hash(bundle.source),
        java_project_hash=project.content_hash(),
        architecture_hash=architecture.content_hash(),
        test_suite_hash=suite.content_hash(),
    )

    cobol_exec: ProgramExecutor = cobol_executor or CobolExecutor(workspace_root)
    java_exec: ProgramExecutor = java_executor or JavaExecutor(workspace_root)

    comparisons = []
    for test in suite.tests:
        if not test.executable:
            not_attempted = ExecutionResult(
                executed=False,
                success=False,
                executor_kind="not_attempted",
                diagnostics=(test.inconclusive_reason or "marked non-executable",),
            )
            comparisons.append(
                compare_observation(
                    test, not_attempted, not_attempted, artifact_versions=versions
                )
            )
            continue

        inputs = {i.name: i.value for i in test.inputs}
        observe = tuple(
            sorted(
                {o.name for o in test.expected_outputs if o.kind == "field"}
                | {s.field for s in test.expected_state_changes}
            )
        )
        cobol_spec = ProgramSpec(
            source_id=bundle.source_id,
            kind="cobol",
            payload=bundle.source,
            observe_fields=observe,
            artifact_version=versions.cobol_source_hash,
        )
        java_spec = ProgramSpec(
            source_id=bundle.source_id,
            kind="java",
            payload=project,
            observe_fields=observe,
            artifact_version=versions.java_project_hash,
        )
        cobol_obs = cobol_exec.execute(cobol_spec, inputs)
        java_obs = java_exec.execute(java_spec, inputs)
        comparisons.append(
            compare_observation(test, cobol_obs, java_obs, artifact_versions=versions)
        )

    real_cobol = isinstance(cobol_exec, CobolExecutor) and cobol_runtime_available()
    real_java = isinstance(java_exec, JavaExecutor) and java_runtime_available()

    return aggregate_report(
        bundle.source_id,
        suite,
        tuple(comparisons),
        real_cobol_execution=real_cobol,
        real_java_execution=real_java,
        cobol_runtime=cobol_compiler_version() if real_cobol else "unavailable",
    )
