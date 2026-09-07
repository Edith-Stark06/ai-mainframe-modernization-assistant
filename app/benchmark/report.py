"""
Deterministic benchmark report generation (#119 §18).

Given a :class:`BenchmarkSuite`, a list of :class:`ExampleScore`, and a
``run_meta`` dict, produce:

* ``summary.json``   — machine-readable aggregate (deterministic; the
  wall-clock ``timestamp`` lives in ``run_meta`` only).
* ``summary.md``     — human-readable.
* ``detailed.jsonl`` — one line per example score.

No undocumented manual arithmetic: every aggregate is a mean / count /
sum over the per-example scores.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.benchmark.models import BenchmarkSuite
from app.benchmark.scoring import ExampleScore

__all__ = ["BenchmarkReport", "generate_report"]


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def _collect_metric(scores: list[ExampleScore], *path: str) -> list[float]:
    out: list[float] = []
    for s in scores:
        node: Any = s.metrics
        ok = True
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                ok = False
                break
        if ok and isinstance(node, (int, float)):
            out.append(float(node))
    return out


_TASK_HEADLINE = {
    "cobol_explanation": ("concept_coverage",),
    "modernization_qa": ("concept_coverage",),
    "source_grounded_qa": ("answer_correct",),
    "business_rule_extraction": ("rule_prf", "f1"),
    "risk_identification": ("risk_prf", "f1"),
    "modernization_recommendation": ("strategy_correct",),
    "cobol_to_structured": ("paragraph_prf", "f1"),
    "cobol_to_java": ("java_structural", "construct_coverage"),
}


@dataclass
class BenchmarkReport:
    summary: dict[str, Any]
    detailed: list[dict[str, Any]]

    def to_summary_json(self) -> str:
        return json.dumps(self.summary, indent=2, sort_keys=True) + "\n"

    def to_detailed_jsonl(self) -> str:
        return (
            "\n".join(
                json.dumps(d, sort_keys=True, separators=(",", ":"))
                for d in self.detailed
            )
            + "\n"
        )

    def to_summary_md(self) -> str:
        s = self.summary
        lines = [
            f"# Benchmark report — {s['benchmark_version']}",
            "",
            f"- model: `{s['run']['model']}`  provider: `{s['run']['provider']}`  "
            f"mode: `{s['run']['mode']}`",
            f"- prompt version: `{s['prompt_version']}`  "
            f"analysis version: `{s['analysis_version']}`  "
            f"dataset version: `{s['dataset_version']}`",
            f"- benchmark content hash: `{s['benchmark_content_hash']}`",
            f"- timestamp: {s['run'].get('timestamp', 'n/a')}",
            "",
            "## Overall",
            "",
            f"- examples: {s['overall']['n']}",
            f"- pass rate: {s['overall']['pass_rate']}",
            f"- hallucination rate (mean per example): "
            f"{s['overall']['hallucination_rate']}",
            f"- mean attribution precision: {s['overall']['attribution_precision']}",
            f"- mean attribution recall: {s['overall']['attribution_recall']}",
            f"- parse-failure rate: {s['overall']['parse_failure_rate']}",
            f"- mean latency (s): {s['run'].get('mean_latency_s', 'unavailable')}",
            f"- total tokens: {s['run'].get('total_tokens', 'unavailable')}",
            f"- estimated cost: {s['run'].get('estimated_cost', 'unavailable')}",
            "",
            "## By task",
            "",
            "| task | n | pass rate | headline metric | hallucinations |",
            "|---|---|---|---|---|",
        ]
        for task, t in sorted(s["by_task"].items()):
            lines.append(
                f"| {task} | {t['n']} | {t['pass_rate']} | "
                f"{t.get('headline_metric', 'n/a')} | {t['hallucination_total']} |"
            )
        lines += [
            "",
            "## By difficulty",
            "",
            "| difficulty | n | pass rate | hallucinations |",
            "|---|---|---|---|",
        ]
        for diff in ("easy", "medium", "difficult", "adversarial"):
            if diff in s["by_difficulty"]:
                d = s["by_difficulty"][diff]
                lines.append(
                    f"| {diff} | {d['n']} | {d['pass_rate']} | {d['hallucination_total']} |"
                )
        lines += ["", "## Failures / hallucinations", ""]
        for f in s["failures"][:25]:
            lines.append(
                f"- `{f['example_id']}` ({f['task_type']}/{f['difficulty']}) — "
                f"passed={f['passed']} hallucinations={f['hallucination_total']} "
                f"{'; '.join(f['notes']) if f['notes'] else ''}"
            )
        return "\n".join(lines) + "\n"

    def write(self, out_dir: str | Path) -> None:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "summary.json").write_text(self.to_summary_json(), encoding="utf-8")
        (d / "summary.md").write_text(self.to_summary_md(), encoding="utf-8")
        (d / "detailed.jsonl").write_text(self.to_detailed_jsonl(), encoding="utf-8")


def generate_report(
    suite: BenchmarkSuite,
    scores: list[ExampleScore],
    run_meta: dict[str, Any],
) -> BenchmarkReport:
    scores = sorted(scores, key=lambda s: s.example_id)
    n = len(scores)

    by_task: dict[str, list[ExampleScore]] = defaultdict(list)
    by_diff: dict[str, list[ExampleScore]] = defaultdict(list)
    for sc in scores:
        by_task[sc.task_type].append(sc)
        by_diff[sc.difficulty].append(sc)

    def block(group: list[ExampleScore]) -> dict[str, Any]:
        return {
            "n": len(group),
            "pass_rate": _mean([1.0 if s.passed else 0.0 for s in group]),
            "hallucination_total": sum(s.hallucination_total for s in group),
            "parse_failure_rate": _mean([0.0 if s.parsed_ok else 1.0 for s in group]),
        }

    task_blocks: dict[str, Any] = {}
    for task, group in by_task.items():
        b = block(group)
        head = _TASK_HEADLINE.get(task)
        if head:
            vals = _collect_metric(group, *head)
            b["headline_metric"] = _mean(vals) if vals else "n/a"
        task_blocks[task] = b

    hall_keys = [
        "incorrect",
        "unsupported_by_source",
        "contradicted_by_source",
        "invented_source_location",
        "invented_dependency",
        "invented_business_rule",
        "invented_risk",
    ]
    hall_totals = {
        k: sum(s.hallucinations.get(k, 0) for s in scores) for k in hall_keys
    }

    summary = {
        "benchmark_version": suite.benchmark_version,
        "benchmark_content_hash": suite.content_hash,
        "prompt_version": run_meta.get("prompt_version", suite.prompt_version),
        "analysis_version": suite.analysis_version,
        "dataset_version": run_meta.get("dataset_version", "n/a"),
        "run": run_meta,
        "overall": {
            "n": n,
            "pass_rate": _mean([1.0 if s.passed else 0.0 for s in scores]),
            "hallucination_rate": _mean([float(s.hallucination_total) for s in scores]),
            "hallucination_totals": hall_totals,
            "attribution_precision": _mean(
                [s.attribution.get("precision", 0.0) for s in scores if s.attribution]
            ),
            "attribution_recall": _mean(
                [s.attribution.get("recall", 0.0) for s in scores if s.attribution]
            ),
            "parse_failure_rate": _mean([0.0 if s.parsed_ok else 1.0 for s in scores]),
        },
        "by_task": task_blocks,
        "by_difficulty": {k: block(v) for k, v in by_diff.items()},
        "failures": [
            {
                "example_id": s.example_id,
                "task_type": s.task_type,
                "difficulty": s.difficulty,
                "passed": s.passed,
                "hallucination_total": s.hallucination_total,
                "notes": s.notes,
            }
            for s in scores
            if (not s.passed) or s.hallucination_total > 0
        ],
    }

    return BenchmarkReport(summary=summary, detailed=[s.to_dict() for s in scores])
