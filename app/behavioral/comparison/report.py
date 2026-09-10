"""
#131 — aggregate the per-test comparisons into a Phase 10 report.

The three-way result (PASS / FAIL / INCONCLUSIVE) is always reported in
full — never collapsed into a single "equivalence percentage" that
quietly excludes inconclusive cases. ``overall_status`` can only be
``BEHAVIORALLY_VERIFIED`` when every test was actually executed on both
sides and passed; a single FAIL or INCONCLUSIVE forces the aggregate
down, even if every *executable* case that could be compared passed.
"""

from __future__ import annotations

from app.behavioral.comparison.models import (
    BehavioralComparison,
    ComparisonStatus,
    OverallStatus,
    Phase10Report,
)
from app.behavioral.extraction.models import BehavioralSuite

__all__ = ["aggregate_report"]


def aggregate_report(
    source_id: str,
    suite: BehavioralSuite,
    comparisons: tuple[BehavioralComparison, ...],
    *,
    real_cobol_execution: bool,
    real_java_execution: bool,
    cobol_runtime: str,
    notes: tuple[str, ...] = (),
) -> Phase10Report:
    pass_n = sum(1 for c in comparisons if c.status is ComparisonStatus.PASS)
    fail_n = sum(1 for c in comparisons if c.status is ComparisonStatus.FAIL)
    inconclusive_n = sum(
        1 for c in comparisons if c.status is ComparisonStatus.INCONCLUSIVE
    )
    cobol_ok = sum(
        1
        for c in comparisons
        if c.cobol_observation.executed and c.cobol_observation.success
    )
    java_ok = sum(
        1
        for c in comparisons
        if c.java_observation.executed and c.java_observation.success
    )

    if fail_n > 0:
        overall = OverallStatus.BEHAVIORAL_DIFFERENCE_FOUND
    elif inconclusive_n > 0 or pass_n == 0:
        overall = OverallStatus.INCONCLUSIVE
    elif not (real_cobol_execution and real_java_execution):
        # every comparison happened to PASS, but at least one side was not
        # a real runtime (e.g. a scripted stand-in used to exercise the
        # comparator) — that proves the PIPELINE, not real-world COBOL/Java
        # equivalence, so the aggregate must not claim BEHAVIORALLY_VERIFIED
        overall = OverallStatus.INCONCLUSIVE
    else:
        overall = OverallStatus.BEHAVIORALLY_VERIFIED

    all_notes = list(notes)
    if not real_cobol_execution:
        all_notes.append(
            "real COBOL execution was not performed for this run — no "
            "individual comparison can be upgraded past what was actually "
            "observed, and the aggregate cannot claim BEHAVIORALLY_VERIFIED"
        )
    if suite.non_executable_tests:
        all_notes.append(
            f"{len(suite.non_executable_tests)} behavioral test case(s) were "
            "marked non-executable by #129 (unsupported COBOL / generator "
            "stub / unreachable paragraph) and are reported INCONCLUSIVE, "
            "not excluded from the totals"
        )

    return Phase10Report(
        source_id=source_id,
        overall_status=overall,
        comparisons=comparisons,
        total_tests=len(suite.tests),
        executable_tests=len(suite.executable_tests),
        non_executable_tests=len(suite.non_executable_tests),
        cobol_execution_successes=cobol_ok,
        java_execution_successes=java_ok,
        pass_count=pass_n,
        fail_count=fail_n,
        inconclusive_count=inconclusive_n,
        real_cobol_execution=real_cobol_execution,
        real_java_execution=real_java_execution,
        cobol_runtime=cobol_runtime,
        notes=tuple(all_notes),
    )
