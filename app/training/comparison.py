"""
Baseline-vs-fine-tuned comparison and the improvement decision
(#121 Parts 10-12).

The decision is deliberately **not** ``candidate_score > baseline_score``.
It weighs:

* overall pass-rate movement against a "meaningful" threshold,
* hallucination / grounding movement,
* per-task regressions that a small overall gain must not paper over,
* sample-size limits (the benchmark is 22 items),
* run health (parse failures, provider failures, example-count mismatch).

Outcomes: ``IMPROVED`` · ``NO_MEANINGFUL_IMPROVEMENT`` · ``REGRESSED`` ·
``INCONCLUSIVE``. Nothing here can be tuned "to make fine-tuning look
good" without changing ``DECISION_POLICY_VERSION`` and this file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.training.evaluation import EvaluationArtifact, require_comparable
from app.training.version import DECISION_POLICY_VERSION

__all__ = [
    "DecisionPolicy",
    "DEFAULT_POLICY",
    "MetricRow",
    "ComparisonResult",
    "compare_models",
    "IMPROVED",
    "NO_MEANINGFUL_IMPROVEMENT",
    "REGRESSED",
    "INCONCLUSIVE",
]

IMPROVED = "IMPROVED"
NO_MEANINGFUL_IMPROVEMENT = "NO_MEANINGFUL_IMPROVEMENT"
REGRESSED = "REGRESSED"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class DecisionPolicy:
    policy_version: str = DECISION_POLICY_VERSION
    #: smallest overall pass-rate change treated as real signal
    min_meaningful_overall_delta: float = 0.05
    #: candidate may add at most this much hallucination before it counts
    #: against it
    hallucination_regression_tolerance: float = 0.02
    #: a per-task pass-rate drop at least this large is a regression
    max_unoffset_task_regression: float = 0.15
    #: ...unless the overall pass-rate gain is at least this large, which
    #: is the only thing that offsets a major per-task regression
    task_regression_offset: float = 0.10
    #: fewer comparable examples than this -> INCONCLUSIVE
    min_examples: int = 20
    #: candidate parse-failure rate above this -> INCONCLUSIVE
    max_parse_failure_rate: float = 0.25
    #: below this example count, always add a sample-size caveat
    small_sample_threshold: int = 40


DEFAULT_POLICY = DecisionPolicy()


@dataclass(frozen=True)
class MetricRow:
    name: str
    baseline: float
    candidate: float
    higher_is_better: bool

    @property
    def delta(self) -> float:
        return round(self.candidate - self.baseline, 4)

    @property
    def direction(self) -> str:
        d = self.delta
        if d == 0:
            return "flat"
        improved = d > 0 if self.higher_is_better else d < 0
        return "better" if improved else "worse"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.name,
            "baseline": round(self.baseline, 4),
            "candidate": round(self.candidate, 4),
            "delta": self.delta,
            "higher_is_better": self.higher_is_better,
            "direction": self.direction,
        }


@dataclass
class ComparisonResult:
    baseline_model_version: str
    finetuned_model_version: str
    benchmark_version: str
    benchmark_content_hash: str
    evaluation_mode: str
    prompt_version: str | None
    decision_policy_version: str
    overall: list[MetricRow]
    per_task: list[MetricRow]
    per_difficulty: list[MetricRow]
    failure_categories: dict[str, dict[str, int]]
    decision: str = INCONCLUSIVE
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_model_version": self.baseline_model_version,
            "finetuned_model_version": self.finetuned_model_version,
            "benchmark_version": self.benchmark_version,
            "benchmark_content_hash": self.benchmark_content_hash,
            "evaluation_mode": self.evaluation_mode,
            "prompt_version": self.prompt_version,
            "decision_policy_version": self.decision_policy_version,
            "decision": self.decision,
            "rationale": self.rationale,
            "overall": [r.to_dict() for r in self.overall],
            "per_task": [r.to_dict() for r in self.per_task],
            "per_difficulty": [r.to_dict() for r in self.per_difficulty],
            "failure_categories": self.failure_categories,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            f"# Baseline vs fine-tuned — {self.benchmark_version}",
            "",
            f"- baseline: `{self.baseline_model_version}`",
            f"- fine-tuned: `{self.finetuned_model_version}`",
            f"- benchmark hash: `{self.benchmark_content_hash}`  "
            f"mode: `{self.evaluation_mode}`  prompt: `{self.prompt_version}`",
            f"- decision policy: `{self.decision_policy_version}`",
            "",
            f"## Decision: **{self.decision}**",
            "",
        ]
        lines += [f"- {r}" for r in self.rationale]
        lines += [
            "",
            "## Overall",
            "",
            "| metric | baseline | fine-tuned | delta |",
            "|---|---|---|---|",
        ]
        for r in self.overall:
            lines.append(
                f"| {r.name} | {r.baseline:.4f} | {r.candidate:.4f} | "
                f"{r.delta:+.4f} ({r.direction}) |"
            )
        for title, rows in (
            ("Per task (pass rate)", self.per_task),
            ("Per difficulty (pass rate)", self.per_difficulty),
        ):
            lines += [
                "",
                f"## {title}",
                "",
                "| key | baseline | fine-tuned | delta |",
                "|---|---|---|---|",
            ]
            for r in rows:
                lines.append(
                    f"| {r.name} | {r.baseline:.4f} | {r.candidate:.4f} | "
                    f"{r.delta:+.4f} ({r.direction}) |"
                )
        lines += [
            "",
            "## Hallucination categories",
            "",
            "| category | baseline | fine-tuned |",
            "|---|---|---|",
        ]
        for cat, v in sorted(self.failure_categories.items()):
            lines.append(f"| {cat} | {v['baseline']} | {v['candidate']} |")
        return "\n".join(lines) + "\n"

    def write(self, out_dir: str | Path) -> Path:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "comparison.json").write_text(self.to_json(), encoding="utf-8")
        (d / "comparison.md").write_text(self.to_markdown(), encoding="utf-8")
        return d


def _overall(summary: dict[str, Any]) -> dict[str, Any]:
    return summary.get("overall", {})


def _task_rows(base: dict[str, Any], cand: dict[str, Any]) -> list[MetricRow]:
    tasks = sorted(set(base.get("by_task", {})) | set(cand.get("by_task", {})))
    rows = []
    for t in tasks:
        rows.append(
            MetricRow(
                name=t,
                baseline=float(
                    base.get("by_task", {}).get(t, {}).get("pass_rate", 0.0)
                ),
                candidate=float(
                    cand.get("by_task", {}).get(t, {}).get("pass_rate", 0.0)
                ),
                higher_is_better=True,
            )
        )
    return rows


def _difficulty_rows(base: dict[str, Any], cand: dict[str, Any]) -> list[MetricRow]:
    rows = []
    for d in ("easy", "medium", "difficult", "adversarial"):
        b = base.get("by_difficulty", {}).get(d)
        c = cand.get("by_difficulty", {}).get(d)
        if b is None and c is None:
            continue
        rows.append(
            MetricRow(
                name=d,
                baseline=float((b or {}).get("pass_rate", 0.0)),
                candidate=float((c or {}).get("pass_rate", 0.0)),
                higher_is_better=True,
            )
        )
    return rows


def compare_models(
    baseline: EvaluationArtifact,
    candidate: EvaluationArtifact,
    *,
    policy: DecisionPolicy = DEFAULT_POLICY,
) -> ComparisonResult:
    require_comparable(baseline, candidate)

    b, c = baseline.summary, candidate.summary
    bo, co = _overall(b), _overall(c)

    overall_rows = [
        MetricRow(
            "pass_rate", bo.get("pass_rate", 0.0), co.get("pass_rate", 0.0), True
        ),
        MetricRow(
            "hallucination_rate",
            bo.get("hallucination_rate", 0.0),
            co.get("hallucination_rate", 0.0),
            False,
        ),
        MetricRow(
            "attribution_precision",
            bo.get("attribution_precision", 0.0),
            co.get("attribution_precision", 0.0),
            True,
        ),
        MetricRow(
            "attribution_recall",
            bo.get("attribution_recall", 0.0),
            co.get("attribution_recall", 0.0),
            True,
        ),
        MetricRow(
            "parse_failure_rate",
            bo.get("parse_failure_rate", 0.0),
            co.get("parse_failure_rate", 0.0),
            False,
        ),
    ]
    task_rows = _task_rows(b, c)
    diff_rows = _difficulty_rows(b, c)

    b_ht = bo.get("hallucination_totals", {})
    c_ht = co.get("hallucination_totals", {})
    failure_categories = {
        k: {"baseline": int(b_ht.get(k, 0)), "candidate": int(c_ht.get(k, 0))}
        for k in sorted(set(b_ht) | set(c_ht))
    }

    result = ComparisonResult(
        baseline_model_version=baseline.model_label,
        finetuned_model_version=candidate.model_label,
        benchmark_version=candidate.benchmark_version,
        benchmark_content_hash=candidate.benchmark_content_hash,
        evaluation_mode=candidate.mode,
        prompt_version=c.get("prompt_version"),
        decision_policy_version=policy.policy_version,
        overall=overall_rows,
        per_task=task_rows,
        per_difficulty=diff_rows,
        failure_categories=failure_categories,
    )
    _decide(result, bo, co, b, c, policy)
    return result


def _decide(
    result: ComparisonResult,
    bo: dict[str, Any],
    co: dict[str, Any],
    b: dict[str, Any],
    c: dict[str, Any],
    policy: DecisionPolicy,
) -> None:
    reasons: list[str] = []
    n_b = int(bo.get("n", 0))
    n_c = int(co.get("n", 0))
    overall_delta = round(co.get("pass_rate", 0.0) - bo.get("pass_rate", 0.0), 4)
    halluc_delta = round(
        co.get("hallucination_rate", 0.0) - bo.get("hallucination_rate", 0.0), 4
    )
    cand_parse_fail = float(co.get("parse_failure_rate", 0.0))
    provider_failures = int(c.get("run", {}).get("provider_failures", 0) or 0)

    task_regressions = [
        (r.name, r.delta)
        for r in result.per_task
        if r.delta <= -policy.max_unoffset_task_regression
    ]
    task_improvements = [
        (r.name, r.delta)
        for r in result.per_task
        if r.delta >= policy.max_unoffset_task_regression
    ]

    # --- INCONCLUSIVE guards -------------------------------------------
    if n_b != n_c:
        result.decision = INCONCLUSIVE
        result.rationale = [
            f"baseline and candidate were scored on a different number of "
            f"examples ({n_b} vs {n_c}) — not comparable."
        ]
        return
    if n_c < policy.min_examples:
        result.decision = INCONCLUSIVE
        result.rationale = [
            f"only {n_c} comparable examples (< {policy.min_examples}); "
            f"insufficient to decide."
        ]
        return
    if provider_failures > 0:
        result.decision = INCONCLUSIVE
        result.rationale = [
            f"candidate run had {provider_failures} provider failure(s); "
            f"re-run before deciding."
        ]
        return
    if cand_parse_fail > policy.max_parse_failure_rate:
        result.decision = INCONCLUSIVE
        result.rationale = [
            f"candidate parse-failure rate {cand_parse_fail:.2f} exceeds "
            f"{policy.max_parse_failure_rate:.2f}; output is not reliably usable."
        ]
        return

    thr = policy.min_meaningful_overall_delta
    tol = policy.hallucination_regression_tolerance

    # --- REGRESSED ----------------------------------------------------
    if overall_delta <= -thr:
        result.decision = REGRESSED
        reasons.append(
            f"overall pass rate fell by {abs(overall_delta):.3f} " f"(>= {thr:.2f})."
        )
    elif halluc_delta > tol and overall_delta < thr:
        result.decision = REGRESSED
        reasons.append(
            f"hallucination rate rose by {halluc_delta:.3f} without a "
            f"compensating pass-rate gain."
        )
    elif task_regressions and overall_delta < policy.task_regression_offset:
        result.decision = REGRESSED
        reasons.append(
            "per-task regression not offset by an overall gain: "
            + ", ".join(f"{t} {d:+.3f}" for t, d in task_regressions)
        )
    # --- IMPROVED ---------------------------------------------------
    elif overall_delta >= thr and halluc_delta <= tol and not task_regressions:
        result.decision = IMPROVED
        reasons.append(
            f"overall pass rate rose by {overall_delta:.3f} (>= {thr:.2f}) "
            f"with no unoffset per-task regression and hallucination within "
            f"tolerance ({halluc_delta:+.3f})."
        )
        if task_improvements:
            reasons.append(
                "task gains: "
                + ", ".join(f"{t} {d:+.3f}" for t, d in task_improvements)
            )
    # --- NO MEANINGFUL IMPROVEMENT --------------------------------
    elif abs(overall_delta) < thr and abs(halluc_delta) <= tol and not task_regressions:
        result.decision = NO_MEANINGFUL_IMPROVEMENT
        reasons.append(
            f"overall pass rate moved {overall_delta:+.3f} (< {thr:.2f}) and "
            f"hallucination moved {halluc_delta:+.3f} (within tolerance); "
            f"no evidence fine-tuning helped — keep the baseline."
        )
    # --- otherwise: mixed ----------------------------------------
    else:
        result.decision = INCONCLUSIVE
        reasons.append(
            f"mixed signals: overall {overall_delta:+.3f}, hallucination "
            f"{halluc_delta:+.3f}, task regressions={bool(task_regressions)}."
        )

    if n_c < policy.small_sample_threshold:
        reasons.append(
            f"sample-size caveat: {n_c} benchmark items — treat small deltas "
            f"as noise; confirm with a larger evaluation set before adoption."
        )
    result.rationale = reasons
