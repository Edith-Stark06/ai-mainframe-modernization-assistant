"""
#120 §25 — capability analysis / fine-tuning assessment.

Given the three per-mode benchmark reports (raw / analysis / retrieval),
produce, per task:

  task | raw pass | analysis pass | retrieval pass | observed failure
       | likely cause | fine-tuning evidence

The verdict is EVIDENCE-DRIVEN, never "we should fine-tune because this
is an AI project":

* if deterministic analysis already lifts a task to a high pass rate,
  the evidence points to *prompting + analysis*, not fine-tuning;
* fine-tuning is only flagged where analysis/retrieval do NOT close the
  gap and the failures are model-reasoning failures (not parser gaps).
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_capability_analysis"]

_HIGH = 0.8
_LOW = 0.5


def _task_pass(report: dict[str, Any], task: str) -> float:
    return float(report.get("by_task", {}).get(task, {}).get("pass_rate", 0.0))


def _dominant_failure(report: dict[str, Any], task: str) -> str:
    notes: list[str] = []
    for f in report.get("failures", []):
        if f["task_type"] == task:
            notes.extend(f.get("notes", []))
            if f["hallucination_total"] > 0:
                notes.append("hallucination")
    if not notes:
        return "none"
    if any("provider_failure" in n for n in notes):
        return "provider_failure"
    if any("parseable JSON" in n for n in notes):
        return "output_format"
    if any("hallucination" in n for n in notes):
        return "hallucination"
    return "reasoning_failure"


_ANALYSIS_DEPENDENT = {
    "business_rule_extraction",
    "risk_identification",
    "modernization_recommendation",
    "cobol_to_structured",
}


def build_capability_analysis(
    raw: dict[str, Any],
    analysis: dict[str, Any],
    retrieval: dict[str, Any],
) -> dict[str, Any]:
    tasks = sorted(
        set(raw.get("by_task", {}))
        | set(analysis.get("by_task", {}))
        | set(retrieval.get("by_task", {}))
    )
    rows: list[dict[str, Any]] = []
    for task in tasks:
        rp = _task_pass(raw, task)
        ap = _task_pass(analysis, task)
        tp = _task_pass(retrieval, task)
        best = max(rp, ap, tp)
        lift_from_context = max(ap, tp) - rp
        fail = _dominant_failure(analysis if ap <= tp else retrieval, task)

        if best >= _HIGH and lift_from_context >= 0.2:
            verdict = "no fine-tuning evidence — deterministic analysis closes the gap"
            cause = "raw model lacks structured evidence; analysis supplies it"
        elif best >= _HIGH:
            verdict = "no fine-tuning evidence — already strong"
            cause = "task is within base capability"
        elif fail in ("output_format",):
            verdict = "no fine-tuning evidence yet — fix prompt/output format first"
            cause = "structured-output formatting, not reasoning"
        elif fail in ("provider_failure",):
            verdict = "inconclusive — provider failures dominate; re-run"
            cause = "infrastructure"
        elif task in _ANALYSIS_DEPENDENT and ap < _LOW and tp < _LOW:
            verdict = (
                "fine-tuning MAY be justified — analysis context did not lift "
                "this task and failures are model-reasoning failures"
            )
            cause = "model does not use / trust the supplied deterministic evidence"
        else:
            verdict = (
                "collect more evidence — partial improvement from context; "
                "not yet a clear fine-tuning case"
            )
            cause = "mixed"

        rows.append(
            {
                "task": task,
                "raw_pass_rate": round(rp, 4),
                "analysis_pass_rate": round(ap, 4),
                "retrieval_pass_rate": round(tp, 4),
                "context_lift": round(lift_from_context, 4),
                "dominant_failure": fail,
                "likely_cause": cause,
                "fine_tuning_evidence": verdict,
            }
        )

    any_ft = any(
        "fine-tuning MAY be justified" in r["fine_tuning_evidence"] for r in rows
    )
    overall = (
        "No task shows clear fine-tuning evidence in this run. Prompting + "
        "deterministic analysis is the higher-leverage next step. Re-evaluate "
        "#121 only after a live-provider baseline confirms the pattern."
        if not any_ft
        else "At least one task may benefit from fine-tuning — see the rows "
        "flagged below. Confirm with a live-provider baseline before "
        "proceeding to #121."
    )

    return {
        "prompt_version": raw.get("prompt_version"),
        "benchmark_version": raw.get("benchmark_version"),
        "analysis_version": raw.get("analysis_version"),
        "providers": {
            "raw": raw.get("run", {}).get("provider"),
            "analysis": analysis.get("run", {}).get("provider"),
            "retrieval": retrieval.get("run", {}).get("provider"),
        },
        "overall_conclusion": overall,
        "per_task": rows,
    }
