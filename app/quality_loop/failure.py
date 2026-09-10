"""
Failure classification (Phase 11).

Normalizes whatever the deterministic pipeline observed — compiler
diagnostics (#127), Java test execution (#130), behavioral comparison
(#131) — into a single :class:`FailureRecord` shape so the rest of the
loop (eligibility, confidence, repair, audit) never has to branch on
"which phase produced this".

Deterministic priority order (documented, not chosen by the LLM):

    PROVENANCE_FAILURE / INFRASTRUCTURE_FAILURE   (safety first)
        > COMPILATION_ERROR
        > EXECUTION_FAILURE / TEST_FAILURE
        > BEHAVIORAL_MISMATCH
        > UNSUPPORTED_BEHAVIOR                     (never auto-repaired)
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.behavioral.comparison.models import ComparisonStatus, Phase10Report
from app.behavioral.javatests.models import JavaTestSuiteResult
from app.java_modernization.architecture.models import SourceRef
from app.java_modernization.compilation.models import (
    CompilationResult,
    DiagnosticSeverity,
)
from app.java_modernization.generation.models import GeneratedProject

__all__ = [
    "FailureCategory",
    "FailureSeverity",
    "FailureRecord",
    "PRIORITY_ORDER",
    "NEVER_AUTO_REPAIRED",
    "classify_failures",
    "prioritize",
    "group_failures",
]


class FailureCategory(str, Enum):
    COMPILATION_ERROR = "COMPILATION_ERROR"
    TEST_FAILURE = "TEST_FAILURE"
    BEHAVIORAL_MISMATCH = "BEHAVIORAL_MISMATCH"
    UNSUPPORTED_BEHAVIOR = "UNSUPPORTED_BEHAVIOR"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    PROVENANCE_FAILURE = "PROVENANCE_FAILURE"


class FailureSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


#: documented, fixed priority — the LLM never picks which failure to
#: address first; the loop always works the lowest index first.
PRIORITY_ORDER: tuple[FailureCategory, ...] = (
    FailureCategory.PROVENANCE_FAILURE,
    FailureCategory.INFRASTRUCTURE_FAILURE,
    FailureCategory.COMPILATION_ERROR,
    FailureCategory.EXECUTION_FAILURE,
    FailureCategory.TEST_FAILURE,
    FailureCategory.BEHAVIORAL_MISMATCH,
    FailureCategory.UNSUPPORTED_BEHAVIOR,
)

#: categories that must never trigger speculative AI repair — they
#: represent a capability gap or a safety gap, not a fixable defect.
NEVER_AUTO_REPAIRED: frozenset[FailureCategory] = frozenset(
    {
        FailureCategory.INFRASTRUCTURE_FAILURE,
        FailureCategory.PROVENANCE_FAILURE,
        FailureCategory.UNSUPPORTED_BEHAVIOR,
    }
)


class FailureRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failure_id: str
    category: FailureCategory
    severity: FailureSeverity
    message: str
    affected_artifact: str | None = None
    source_mapping: SourceRef | None = None
    business_rule_ids: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _fid(*parts: str) -> str:
    h = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"FAIL-{h[:10]}"


def _from_compilation(compilation: CompilationResult | None) -> list[FailureRecord]:
    if compilation is None:
        return []
    out: list[FailureRecord] = []
    for d in compilation.diagnostics:
        if d.severity is not DiagnosticSeverity.ERROR:
            continue
        out.append(
            FailureRecord(
                failure_id=_fid("compile", d.file or "", str(d.line), d.message),
                category=FailureCategory.COMPILATION_ERROR,
                severity=FailureSeverity.HIGH,
                message=d.message,
                affected_artifact=d.file,
                source_mapping=d.cobol_source_mapping,
                business_rule_ids=d.business_rule_ids,
                evidence=(f"javac: {d.file}:{d.line}: {d.message}",),
            )
        )
    return out


def _from_java_tests(
    result: JavaTestSuiteResult | None, *, default_artifact: str | None
) -> list[FailureRecord]:
    if result is None:
        return []
    if not result.compiled:
        # already captured via _from_compilation when the harness project's
        # compilation is passed in too; if only the test-suite result is
        # available, surface it as a compile failure so it is never lost.
        return [
            FailureRecord(
                failure_id=_fid("harness-compile", result.source_id),
                category=FailureCategory.COMPILATION_ERROR,
                severity=FailureSeverity.HIGH,
                message="generated behavior harness failed to compile",
                affected_artifact=None,
                evidence=tuple(result.compile_diagnostics),
            )
        ]
    art_by_id = {a.test_id: a for a in result.artifacts}
    out: list[FailureRecord] = []
    for run in result.runs:
        art = art_by_id.get(run.test_id)
        # the harness file itself (art.file_path) is generated scaffolding,
        # never the right patch target -- the actual generated business
        # logic lives in the main class file.
        if not run.execution_ok:
            out.append(
                FailureRecord(
                    failure_id=_fid("exec", result.source_id, run.test_id),
                    category=FailureCategory.EXECUTION_FAILURE,
                    severity=FailureSeverity.HIGH,
                    message=f"test {run.test_id} did not execute to completion",
                    affected_artifact=default_artifact,
                    source_mapping=(
                        art.source_refs[0] if art and art.source_refs else None
                    ),
                    business_rule_ids=art.business_rule_ids if art else (),
                    evidence=run.diagnostics or (run.stderr[:500],),
                )
            )
        elif run.assertion_passed is False:
            out.append(
                FailureRecord(
                    failure_id=_fid("assert", result.source_id, run.test_id),
                    category=FailureCategory.TEST_FAILURE,
                    severity=FailureSeverity.HIGH,
                    message=f"test {run.test_id} self-assertion failed: "
                    f"{', '.join(run.failed_fields)}",
                    affected_artifact=default_artifact,
                    source_mapping=(
                        art.source_refs[0] if art and art.source_refs else None
                    ),
                    business_rule_ids=art.business_rule_ids if art else (),
                    evidence=(f"failed fields: {list(run.failed_fields)}",),
                )
            )
    return out


_UNSUPPORTED_MARKERS = ("BE009", "unsupported", "PERFORMed", "marked non-executable")
_INFRA_MARKERS = ("not executed", "runtime unavailable", "not found on PATH")


def _from_behavioral(
    report: Phase10Report | None, *, default_artifact: str | None
) -> list[FailureRecord]:
    if report is None:
        return []
    out: list[FailureRecord] = []
    for c in report.comparisons:
        if c.status is ComparisonStatus.FAIL:
            for diff in c.differences:
                out.append(
                    FailureRecord(
                        failure_id=_fid("behavior", c.comparison_id, diff.field),
                        category=FailureCategory.BEHAVIORAL_MISMATCH,
                        severity=FailureSeverity.CRITICAL,
                        message=(
                            f"{diff.field}: COBOL={diff.cobol_value!r} "
                            f"Java={diff.java_value!r}"
                        ),
                        affected_artifact=default_artifact,
                        source_mapping=diff.source_ref,
                        business_rule_ids=(
                            (diff.business_rule_id,) if diff.business_rule_id else ()
                        ),
                        evidence=(c.reason,),
                    )
                )
            if not c.differences:
                out.append(
                    FailureRecord(
                        failure_id=_fid("behavior", c.comparison_id, "unknown"),
                        category=FailureCategory.BEHAVIORAL_MISMATCH,
                        severity=FailureSeverity.CRITICAL,
                        message=c.reason,
                        affected_artifact=default_artifact,
                        source_mapping=c.source_refs[0] if c.source_refs else None,
                        business_rule_ids=c.business_rule_ids,
                        evidence=(c.reason,),
                    )
                )
        elif c.status is ComparisonStatus.INCONCLUSIVE:
            reason = c.reason or ""
            if any(m in reason for m in _INFRA_MARKERS):
                category = FailureCategory.INFRASTRUCTURE_FAILURE
            elif any(m in reason for m in _UNSUPPORTED_MARKERS):
                category = FailureCategory.UNSUPPORTED_BEHAVIOR
            elif not c.source_refs:
                category = FailureCategory.PROVENANCE_FAILURE
            else:
                category = FailureCategory.UNSUPPORTED_BEHAVIOR
            out.append(
                FailureRecord(
                    failure_id=_fid("inconclusive", c.comparison_id),
                    category=category,
                    severity=FailureSeverity.MEDIUM,
                    message=reason,
                    affected_artifact=default_artifact,
                    source_mapping=c.source_refs[0] if c.source_refs else None,
                    business_rule_ids=c.business_rule_ids,
                    evidence=(reason,),
                )
            )
    return out


def classify_failures(
    *,
    compilation: CompilationResult | None = None,
    java_tests: JavaTestSuiteResult | None = None,
    behavioral: Phase10Report | None = None,
    project: GeneratedProject | None = None,
) -> tuple[FailureRecord, ...]:
    """Turn raw pipeline outputs into a normalized, deterministic failure list.

    ``project``, when given, supplies the "affected artifact" for
    TEST_FAILURE / EXECUTION_FAILURE / BEHAVIORAL_MISMATCH failures: those
    carry no precise per-line Java location (unlike a compiler diagnostic),
    so the actionable target is the generated main class file itself.
    """
    default_artifact = f"src/{project.main_class}.java" if project else None
    failures = (
        _from_compilation(compilation)
        + _from_java_tests(java_tests, default_artifact=default_artifact)
        + _from_behavioral(behavioral, default_artifact=default_artifact)
    )
    # provenance failure: any failure claiming COMPILATION_ERROR/TEST_FAILURE/
    # BEHAVIORAL_MISMATCH severity but with no source mapping cannot be
    # targeted-repaired safely — downgrade its category so eligibility and
    # human-review policy treat it correctly.
    normalized = []
    for f in failures:
        if (
            f.category
            in (
                FailureCategory.COMPILATION_ERROR,
                FailureCategory.TEST_FAILURE,
                FailureCategory.BEHAVIORAL_MISMATCH,
            )
            and f.source_mapping is None
        ):
            normalized.append(
                f.model_copy(
                    update={
                        "category": FailureCategory.PROVENANCE_FAILURE,
                        "evidence": (
                            *f.evidence,
                            "no COBOL source mapping was available for this failure",
                        ),
                    }
                )
            )
        else:
            normalized.append(f)
    return tuple(prioritize(normalized))


def prioritize(failures: list[FailureRecord]) -> list[FailureRecord]:
    """Deterministic priority order — never chosen by the model."""
    return sorted(
        failures,
        key=lambda f: (PRIORITY_ORDER.index(f.category), f.failure_id),
    )


def group_failures(
    failures: tuple[FailureRecord, ...],
) -> tuple[tuple[FailureRecord, ...], ...]:
    """Group failures by affected artifact so one coherent group is repaired
    at a time — never every unrelated failure sent to the model at once."""
    groups: dict[str, list[FailureRecord]] = {}
    order: list[str] = []
    for f in failures:
        key = (
            f.affected_artifact
            or (f.source_mapping.source_path if f.source_mapping else None)
            or f.failure_id
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)
    return tuple(tuple(groups[k]) for k in order)
