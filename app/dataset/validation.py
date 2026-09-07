"""
Dataset validation (#118 §8).

Three checks over a dataset JSONL file, each producing actionable issues:

* **Schema** — every line parses and validates against
  :class:`~app.dataset.schema.DatasetExample` (task type, difficulty,
  versions, source locations, expected-output structure, metadata
  consistency).
* **Duplicates** — exact example, duplicate content (normalised source +
  question + expected output), duplicate ``example_id``.
* **Malformed** — empty source, empty required answer, invalid analysis
  structure, unresolvable source locations, inconsistent metadata.

Plus a security scan (:mod:`app.dataset.security`) over every source and
free-text answer. A ``HIGH`` secret finding fails validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.dataset.io import read_jsonl_raw
from app.dataset.schema import DatasetExample
from app.dataset.security import SecretFinding, SecretScanConfig, SecretScanner

__all__ = [
    "IssueSeverity",
    "ValidationIssue",
    "ValidationReport",
    "validate_dataset",
]


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    line: int
    example_id: str
    code: str
    severity: IssueSeverity
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "example_id": self.example_id,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    path: str
    dataset_version: str | None
    total: int = 0
    valid: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)
    secret_findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity is IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity is IssueSeverity.WARNING)

    @property
    def ok(self) -> bool:
        return self.error_count == 0 and not self.secret_findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "dataset_version": self.dataset_version,
            "total": self.total,
            "valid": self.valid,
            "ok": self.ok,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
            "secret_findings": self.secret_findings,
        }


def _err(line: int, eid: str, code: str, msg: str) -> ValidationIssue:
    return ValidationIssue(line, eid, code, IssueSeverity.ERROR, msg)


def _warn(line: int, eid: str, code: str, msg: str) -> ValidationIssue:
    return ValidationIssue(line, eid, code, IssueSeverity.WARNING, msg)


def validate_dataset(
    path: str | Path,
    secret_config: SecretScanConfig | None = None,
    expected_version: str | None = None,
) -> ValidationReport:
    p = Path(path)
    report = ValidationReport(path=str(p), dataset_version=None)
    scanner = SecretScanner(secret_config)

    seen_ids: dict[str, int] = {}
    seen_content: dict[str, int] = {}
    seen_exact: dict[str, int] = {}
    versions: set[str] = set()

    try:
        rows = list(read_jsonl_raw(p))
    except FileNotFoundError:
        report.issues.append(_err(0, "", "file_not_found", f"no such file: {p}"))
        return report
    except json.JSONDecodeError as exc:
        report.issues.append(_err(0, "", "invalid_jsonl", str(exc)))
        return report

    report.total = len(rows)

    for lineno, data in rows:
        eid = str(data.get("example_id", "?"))

        # -- schema -----------------------------------------------------
        try:
            ex = DatasetExample.model_validate(data)
        except ValidationError as exc:
            for e in exc.errors():
                loc = ".".join(str(x) for x in e.get("loc", ()))
                report.issues.append(
                    _err(lineno, eid, "schema", f"{loc}: {e.get('msg')}")
                )
            continue

        versions.add(ex.dataset_version)

        # -- duplicates ----------------------------------------------
        if ex.example_id in seen_ids:
            report.issues.append(
                _err(
                    lineno,
                    ex.example_id,
                    "duplicate_example_id",
                    f"also on line {seen_ids[ex.example_id]}",
                )
            )
        else:
            seen_ids[ex.example_id] = lineno

        exact = json.dumps(data, sort_keys=True)
        if exact in seen_exact:
            report.issues.append(
                _err(
                    lineno,
                    ex.example_id,
                    "exact_duplicate",
                    f"identical to line {seen_exact[exact]}",
                )
            )
        else:
            seen_exact[exact] = lineno

        ckey = ex.dedup_key()
        if ckey in seen_content:
            report.issues.append(
                _warn(
                    lineno,
                    ex.example_id,
                    "content_duplicate",
                    f"same task/source/question/answer as line {seen_content[ckey]}",
                )
            )
        else:
            seen_content[ckey] = lineno

        # -- malformed / consistency --------------------------------
        report.issues.extend(_malformed_checks(lineno, ex))

        # -- security ---------------------------------------------------
        findings: list[SecretFinding] = list(scanner.scan(ex.input.source))
        for block in _free_text_answers(ex.expected_output):
            findings += scanner.scan(block)
        for f in findings:
            entry = {"line": lineno, "example_id": ex.example_id, **f.to_dict()}
            if f.severity.value == "high":
                report.secret_findings.append(entry)
                report.issues.append(
                    _err(
                        lineno,
                        ex.example_id,
                        "secret",
                        f"{f.pattern} at source line {f.line} ({f.detail})",
                    )
                )
            else:
                report.issues.append(
                    _warn(
                        lineno,
                        ex.example_id,
                        "secret_low",
                        f"{f.pattern} at source line {f.line} ({f.detail})",
                    )
                )

        if all(
            i.severity is not IssueSeverity.ERROR
            for i in report.issues
            if i.line == lineno
        ):
            report.valid += 1

    if len(versions) > 1:
        report.issues.append(
            _err(
                0,
                "",
                "mixed_versions",
                f"file mixes dataset versions: {sorted(versions)}",
            )
        )
    report.dataset_version = next(iter(versions)) if len(versions) == 1 else None
    if expected_version and report.dataset_version != expected_version:
        report.issues.append(
            _err(
                0,
                "",
                "unexpected_version",
                f"expected {expected_version}, got {report.dataset_version}",
            )
        )

    return report


def _malformed_checks(lineno: int, ex: DatasetExample) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not ex.input.source.strip():
        issues.append(_err(lineno, ex.example_id, "empty_source", "source is blank"))

    # analysis structure: list fields must be lists, dict fields dicts
    a = ex.analysis
    for name in ("dependencies", "business_rules", "risks"):
        v = getattr(a, name)
        if v is not None and not isinstance(v, list):
            issues.append(
                _err(
                    lineno, ex.example_id, "bad_analysis", f"analysis.{name} not a list"
                )
            )
    for name in ("ast", "ir", "cfg", "strategy", "coverage", "confidence"):
        v = getattr(a, name)
        if v is not None and not isinstance(v, dict):
            issues.append(
                _err(
                    lineno, ex.example_id, "bad_analysis", f"analysis.{name} not a dict"
                )
            )

    # a QA example must carry a question
    from app.dataset.schema import TaskType

    if ex.task_type in (TaskType.MODERNIZATION_QA, TaskType.SOURCE_GROUNDED_QA):
        if not str(ex.input.context.get("question", "")).strip():
            issues.append(
                _err(
                    lineno,
                    ex.example_id,
                    "missing_question",
                    "QA example has no question",
                )
            )

    # deterministic ground truth should carry an analysis block
    from app.dataset.schema import GroundTruthStatus

    if (
        ex.metadata.ground_truth_status is GroundTruthStatus.DETERMINISTIC
        and ex.task_type is not TaskType.COBOL_TO_STRUCTURED
        and all(getattr(a, f) is None for f in type(a).model_fields)
    ):
        issues.append(
            _warn(
                lineno,
                ex.example_id,
                "deterministic_without_analysis",
                "deterministic label but no analysis block attached",
            )
        )

    return issues


def _free_text_answers(expected: dict[str, Any]) -> list[str]:
    out: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(expected)
    return out
