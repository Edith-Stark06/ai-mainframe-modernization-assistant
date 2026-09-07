"""
Leakage detection between dataset splits (#118 §10).

Checks every pair of splits (train↔validation, train↔test, validation↔test)
for evidence that the same program / question / answer appears on both
sides — which would artificially inflate later model scores.

Checks performed:

* **shared source_id / program identity** — the primary guard; any hit
  is a hard failure.
* identical normalised source text.
* identical question.
* identical expected output.
* source token-shingle fingerprint overlap above a threshold
  (near-duplicate source fragments).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.dataset.schema import DatasetExample

__all__ = ["LeakageHit", "LeakageReport", "detect_leakage"]

_SHINGLE = 5
_NEAR_DUP_THRESHOLD = 0.85


@dataclass(frozen=True)
class LeakageHit:
    kind: str
    severity: str  # "error" | "warning"
    split_a: str
    split_b: str
    key: str
    example_ids: tuple[str, ...]
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "split_a": self.split_a,
            "split_b": self.split_b,
            "key": self.key,
            "example_ids": list(self.example_ids),
            "detail": self.detail,
        }


@dataclass
class LeakageReport:
    hits: list[LeakageHit] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for h in self.hits if h.severity == "error")

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": self.error_count,
            "warning_count": sum(1 for h in self.hits if h.severity == "warning"),
            "hits": [h.to_dict() for h in self.hits],
        }


def _norm_source(ex: DatasetExample) -> str:
    return ex.normalized_source()


def _question(ex: DatasetExample) -> str:
    return " ".join(str(ex.input.context.get("question", "")).split()).lower()


def _expected_hash(ex: DatasetExample) -> str:
    import json

    return hashlib.sha256(
        json.dumps(ex.expected_output, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _is_trivial_expected(ex: DatasetExample) -> bool:
    """
    A "negative" / near-empty answer (no rules, no risks, no unsupported
    syntax, empty lists). Two different programs legitimately sharing such
    an answer is not leakage — it is just two simple programs.
    """
    import json

    eo = ex.expected_output
    flat = json.dumps(eo, sort_keys=True, separators=(",", ":"))
    if flat in ('{"business_rules":[],"rule_count":0}', '{"risks":[],"risk_count":0}'):
        return True
    ans = eo.get("answer")
    if isinstance(ans, dict):
        if ans.get("has_unsupported_syntax") is False and not ans.get("codes"):
            return True
        if ans.get("business_rules") == []:
            return True
        if ans.get("external_calls") == []:
            return True
    return False


def _shingles(text: str) -> set[str]:
    tokens = text.split()
    if len(tokens) < _SHINGLE:
        return {" ".join(tokens)} if tokens else set()
    return {
        " ".join(tokens[i : i + _SHINGLE]) for i in range(len(tokens) - _SHINGLE + 1)
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


def _index(
    examples: Iterable[DatasetExample], keyfn
) -> dict[str, list[DatasetExample]]:
    idx: dict[str, list[DatasetExample]] = {}
    for ex in examples:
        k = keyfn(ex)
        if not k:
            continue
        idx.setdefault(k, []).append(ex)
    return idx


def detect_leakage(
    train: list[DatasetExample],
    validation: list[DatasetExample],
    test: list[DatasetExample],
) -> LeakageReport:
    report = LeakageReport()
    splits = {"train": train, "validation": validation, "test": test}
    names = ["train", "validation", "test"]

    for i, a_name in enumerate(names):
        for b_name in names[i + 1 :]:
            a = splits[a_name]
            b = splits[b_name]
            _pairwise(report, a_name, a, b_name, b)

    report.hits.sort(key=lambda h: (h.severity, h.kind, h.split_a, h.split_b, h.key))
    return report


def _pairwise(
    report: LeakageReport,
    a_name: str,
    a: list[DatasetExample],
    b_name: str,
    b: list[DatasetExample],
) -> None:
    # shared source_id (hard failure)
    a_src = {e.input.source_id for e in a}
    b_src = {e.input.source_id for e in b}
    for sid in sorted(a_src & b_src):
        report.hits.append(
            LeakageHit(
                kind="shared_source_id",
                severity="error",
                split_a=a_name,
                split_b=b_name,
                key=sid,
                example_ids=tuple(
                    sorted(e.example_id for e in a + b if e.input.source_id == sid)
                ),
                detail="same COBOL program appears in both splits",
            )
        )

    # identical normalised source
    a_idx = _index(a, _norm_source)
    for k, b_group in _index(b, _norm_source).items():
        if k in a_idx:
            report.hits.append(
                LeakageHit(
                    kind="identical_source",
                    severity="error",
                    split_a=a_name,
                    split_b=b_name,
                    key=hashlib.sha1(k.encode()).hexdigest()[:12],
                    example_ids=tuple(sorted(e.example_id for e in a_idx[k] + b_group)),
                    detail="whitespace-normalised source text is identical",
                )
            )

    # identical question
    aq = _index(a, _question)
    for k, b_group in _index(b, _question).items():
        if k in aq:
            report.hits.append(
                LeakageHit(
                    kind="identical_question",
                    severity="warning",
                    split_a=a_name,
                    split_b=b_name,
                    key=k[:60],
                    example_ids=tuple(sorted(e.example_id for e in aq[k] + b_group)),
                )
            )

    # identical expected output (ignoring trivial "negative" answers that
    # two unrelated simple programs legitimately share)
    ae = _index([e for e in a if not _is_trivial_expected(e)], _expected_hash)
    for k, b_group_all in _index(
        [e for e in b if not _is_trivial_expected(e)], _expected_hash
    ).items():
        b_group = b_group_all
        if k in ae:
            report.hits.append(
                LeakageHit(
                    kind="identical_expected_output",
                    severity="warning",
                    split_a=a_name,
                    split_b=b_name,
                    key=k[:12],
                    example_ids=tuple(sorted(e.example_id for e in ae[k] + b_group)),
                )
            )

    # near-duplicate source fragments
    a_by_src: dict[str, set[str]] = {}
    for e in a:
        a_by_src.setdefault(e.input.source_id, _shingles(_norm_source(e)))
    b_by_src: dict[str, set[str]] = {}
    for e in b:
        b_by_src.setdefault(e.input.source_id, _shingles(_norm_source(e)))
    for a_sid, a_sh in a_by_src.items():
        for b_sid, b_sh in b_by_src.items():
            sim = _jaccard(a_sh, b_sh)
            if sim >= _NEAR_DUP_THRESHOLD:
                report.hits.append(
                    LeakageHit(
                        kind="near_duplicate_source",
                        severity="error" if sim >= 0.98 else "warning",
                        split_a=a_name,
                        split_b=b_name,
                        key=f"{a_sid}~{b_sid}",
                        example_ids=(a_sid, b_sid),
                        detail=f"source shingle similarity {sim:.2f}",
                    )
                )
