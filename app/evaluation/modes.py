"""
The three #120 evaluation modes (§21).

Only the *context* handed to the model differs between modes — the
benchmark, questions, metrics, scoring and report are identical.

* ``RAW``       — the COBOL source only.
* ``ANALYSIS``  — source + a compact rendering of the FULL deterministic
  Phase 1-5 analysis already attached to the benchmark example.
* ``RETRIEVAL`` — source + only the analysis slice relevant to this
  example's task/question. This is a minimal deterministic selector (no
  embeddings, no vector store) — #122 is RAG, and this is deliberately
  not that.
"""

from __future__ import annotations

import json
from enum import Enum

from app.benchmark.models import BenchmarkExample
from app.dataset.schema import TaskType

__all__ = ["EvalMode", "build_context"]


class EvalMode(str, Enum):
    RAW = "raw"
    ANALYSIS = "analysis"
    RETRIEVAL = "retrieval"


def _fmt(title: str, obj: object) -> str:
    if obj in (None, [], {}):
        return ""
    return f"\n### {title}\n```json\n{json.dumps(obj, indent=2, sort_keys=True)}\n```\n"


def _full_analysis(example: BenchmarkExample) -> str:
    a = example.analysis
    parts = [
        _fmt("Dependencies (deterministic)", a.dependencies),
        _fmt("Business rules (deterministic, #112)", a.business_rules),
        _fmt("Modernization risks (deterministic, #113)", a.risks),
        _fmt("Modernization strategy (deterministic, #114)", a.strategy),
        _fmt("Analysis coverage (#115)", a.coverage),
        _fmt("CFG", a.cfg),
    ]
    return "".join(p for p in parts if p)


_TASK_SLICE = {
    TaskType.BUSINESS_RULE_EXTRACTION: ("business_rules", "ast"),
    TaskType.RISK_IDENTIFICATION: ("risks", "dependencies", "coverage"),
    TaskType.MODERNIZATION_RECOMMENDATION: (
        "strategy",
        "risks",
        "business_rules",
    ),
    TaskType.COBOL_TO_STRUCTURED: ("ast", "cfg", "dependencies"),
    TaskType.COBOL_TO_JAVA: ("ast", "ir", "dependencies"),
    TaskType.COBOL_EXPLANATION: ("ast", "dependencies", "cfg"),
    TaskType.MODERNIZATION_QA: ("strategy", "business_rules", "dependencies"),
    TaskType.SOURCE_GROUNDED_QA: ("dependencies", "coverage", "ast"),
}

_SLICE_TITLES = {
    "ast": "AST (deterministic)",
    "ir": "IR (deterministic)",
    "cfg": "CFG (deterministic, #110)",
    "dependencies": "Dependencies (deterministic, #111)",
    "business_rules": "Business rules (deterministic, #112)",
    "risks": "Modernization risks (deterministic, #113)",
    "strategy": "Modernization strategy (deterministic, #114)",
    "coverage": "Analysis coverage (#115)",
}


def _retrieved_analysis(example: BenchmarkExample) -> str:
    a = example.analysis
    fields = _TASK_SLICE.get(example.task_type, ("ast",))
    q = str(example.input.context.get("question", "")).lower()
    # question-aware tightening for QA
    if example.task_type in (TaskType.SOURCE_GROUNDED_QA, TaskType.MODERNIZATION_QA):
        if "call" in q or "dependen" in q or "external" in q:
            fields = ("dependencies",)
        elif "rule" in q:
            fields = ("business_rules",)
        elif "unsupported" in q or "support" in q:
            fields = ("coverage",)
        elif "strateg" in q:
            fields = ("strategy",)
    out = []
    for f in fields:
        out.append(_fmt(_SLICE_TITLES.get(f, f), getattr(a, f)))
    return "".join(p for p in out if p)


def build_context(mode: EvalMode, example: BenchmarkExample) -> str:
    src = example.input.source
    header = f"## COBOL source ({example.input.source_id})\n```cobol\n{src}\n```\n"
    if mode is EvalMode.RAW:
        return header
    if mode is EvalMode.ANALYSIS:
        body = _full_analysis(example)
        return header + (
            "\n## Deterministic analysis (Phases 1-5)\n" + body if body else header
        )
    if mode is EvalMode.RETRIEVAL:
        body = _retrieved_analysis(example)
        return header + (
            "\n## Retrieved deterministic evidence\n" + body if body else ""
        )
    raise ValueError(mode)
