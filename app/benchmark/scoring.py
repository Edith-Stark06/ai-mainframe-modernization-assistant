"""
Benchmark scoring (#119).

``score_example(example, model_output)`` -> :class:`ExampleScore`.

The model output is parsed defensively: structured tasks expect a JSON
object (a fenced ```json block is unwrapped); free-text tasks
(explanation / QA prose) are scored on the raw text. Parse failure is
itself recorded (it is not silently a zero).

All scoring is deterministic given ``(example, model_output)``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.benchmark.metrics import (
    attribution,
    concept_coverage,
    hallucination_breakdown,
    java_structural_coverage,
    normalize_token,
    prf,
    risk_match_prf,
    rule_match_prf,
    strategy_correctness,
    unsupported_terms,
)
from app.benchmark.models import BenchmarkExample
from app.dataset.schema import TaskType

__all__ = ["ExampleScore", "score_example"]

_STRUCTURED = {
    TaskType.BUSINESS_RULE_EXTRACTION,
    TaskType.RISK_IDENTIFICATION,
    TaskType.MODERNIZATION_RECOMMENDATION,
    TaskType.COBOL_TO_STRUCTURED,
    TaskType.COBOL_TO_JAVA,
}

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class ExampleScore:
    example_id: str
    task_type: str
    difficulty: str
    parsed_ok: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    hallucinations: dict[str, int] = field(default_factory=dict)
    attribution: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "task_type": self.task_type,
            "difficulty": self.difficulty,
            "parsed_ok": self.parsed_ok,
            "metrics": self.metrics,
            "hallucinations": self.hallucinations,
            "attribution": self.attribution,
            "passed": self.passed,
            "notes": self.notes,
        }

    @property
    def hallucination_total(self) -> int:
        return sum(self.hallucinations.values())


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = _JSON_BLOCK.search(text)
    candidate = m.group(1) if m else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
    if candidate is None:
        return None
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _analysis_vocab(example: BenchmarkExample) -> set[str]:
    vocab: set[str] = set()
    a = example.analysis
    src = example.input.source
    for word in re.findall(r"[A-Za-z0-9_\-]+", src):
        vocab.add(normalize_token(word))
    for group in (a.dependencies or [], a.business_rules or [], a.risks or []):
        vocab |= _walk_strings(group)
    for d in (a.ast, a.ir, a.cfg, a.strategy, a.coverage):
        if d:
            vocab |= _walk_strings(d)
    return vocab


def _walk_strings(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, str):
        for w in re.findall(r"[A-Za-z0-9_\-]+", obj):
            out.add(normalize_token(w))
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _walk_strings(v)
    return out


def score_example(example: BenchmarkExample, model_output: str) -> ExampleScore:
    task = example.task_type
    rubric = example.rubric
    src = example.input.source
    line_count = len(src.splitlines())
    notes: list[str] = []

    parsed: dict[str, Any] | None = None
    if task in _STRUCTURED:
        parsed = _extract_json(model_output)
        if parsed is None:
            notes.append("model output was not parseable JSON")

    metrics: dict[str, Any] = {}
    hall = {
        "incorrect": 0,
        "unsupported_by_source": 0,
        "invented_source_location": 0,
        "invented_dependency": 0,
        "invented_business_rule": 0,
        "invented_risk": 0,
    }
    attr = {"precision": 0.0, "recall": 0.0, "invented": 0}

    vocab = _analysis_vocab(example)

    # -- per-task ------------------------------------------------------
    if task in (TaskType.COBOL_EXPLANATION, TaskType.MODERNIZATION_QA):
        required = list(rubric.get("required_concepts", []))
        cov = concept_coverage(model_output, required)
        forbidden = [normalize_token(t) for t in rubric.get("forbidden_terms", [])]
        said_forbidden = sorted(
            t
            for t in forbidden
            if t in {normalize_token(w) for w in model_output.split()}
        )
        invented_ids = [
            t for t in unsupported_terms(model_output, vocab) if t not in required
        ]
        metrics = {
            "concept_coverage": round(cov, 4),
            "said_forbidden_terms": said_forbidden,
            "invented_identifiers": invented_ids,
        }
        hall["unsupported_by_source"] = len(invented_ids)
        hall["contradicted_by_source"] = len(said_forbidden)
        metrics["unsupported_claim_rate"] = round(
            (len(invented_ids) + len(said_forbidden))
            / max(1, len(model_output.split()) / 20),
            4,
        )
        passed = (
            cov >= rubric.get("min_concept_coverage", 0.6)
            and not said_forbidden
            and len(invented_ids) <= rubric.get("max_invented_identifiers", 0)
        )

    elif task == TaskType.SOURCE_GROUNDED_QA:
        gold_ans = example.expected_output.get("answer", {})
        parsed_qa = _extract_json(model_output) or {}
        ans = parsed_qa.get("answer", parsed_qa)
        exact = _answers_match(ans, gold_ans)
        cites = parsed_qa.get("citations", parsed_qa.get("source_locations", []))
        cites = _normalize_citations(cites)
        at = attribution(
            cites, src, [loc.model_dump() for loc in example.source_locations]
        )
        attr = at.to_dict()
        cited_lines = [c["line"] for c in cites if isinstance(c.get("line"), int)]
        hall["invented_source_location"] = sum(
            1 for ln in cited_lines if ln < 1 or ln > line_count
        )
        metrics = {
            "answer_correct": 1.0 if exact else 0.0,
            "n_citations": len(cites),
        }
        if rubric.get("answer_is_not_determinable"):
            # honest answer: acknowledge it cannot be determined -- either
            # in prose or as a structured {"determinable": false}.
            structured_ack = isinstance(ans, dict) and ans.get("determinable") is False
            acknowledged = structured_ack or _acknowledges_uncertainty(model_output)
            metrics["acknowledged_uncertainty"] = 1.0 if acknowledged else 0.0
            passed = acknowledged and hall["invented_source_location"] == 0
            if not acknowledged:
                hall["unsupported_by_source"] = 1
        else:
            min_ap = rubric.get("min_attribution_precision", 0.5)
            if min_ap <= 0.0:
                # this grounded question has no line-level evidence
                # (e.g. "which unsupported constructs?") — score on the
                # answer alone.
                attr_ok = True
            else:
                attr_ok = len(cites) >= 1 and at.precision >= min_ap
            passed = exact and attr_ok and hall["invented_source_location"] == 0

    elif task == TaskType.BUSINESS_RULE_EXTRACTION:
        gold = example.expected_output.get("business_rules", [])
        pred = (parsed or {}).get("business_rules", []) if parsed else []
        r = rule_match_prf(pred, gold)
        metrics = {
            "rule_prf": r.to_dict(),
            "n_predicted": len(pred),
            "n_gold": len(gold),
        }
        from app.benchmark.metrics import _rule_key  # noqa: PLC0415

        hall["invented_business_rule"] = len(
            {_rule_key(x) for x in pred} - {_rule_key(x) for x in gold}
        )
        passed = bool(parsed) and r.f1 >= rubric.get("min_f1", 0.6)

    elif task == TaskType.RISK_IDENTIFICATION:
        gold = example.expected_output.get("risks", [])
        pred = (parsed or {}).get("risks", []) if parsed else []
        r = risk_match_prf(pred, gold)
        metrics = {
            "risk_prf": r.to_dict(),
            "n_predicted": len(pred),
            "n_gold": len(gold),
        }
        from app.benchmark.metrics import _risk_key  # noqa: PLC0415

        hall["invented_risk"] = len(
            {_risk_key(x) for x in pred} - {_risk_key(x) for x in gold}
        )
        passed = bool(parsed) and r.f1 >= rubric.get("min_f1", 0.5)

    elif task == TaskType.MODERNIZATION_RECOMMENDATION:
        gold_primary = (example.expected_output.get("primary") or {}).get("strategy")
        pred_primary = (
            ((parsed or {}).get("primary") or {}).get("strategy") if parsed else None
        )
        if pred_primary is None and parsed:
            pred_primary = parsed.get("strategy")
        sc = strategy_correctness(pred_primary, gold_primary)
        gold_prereq = set(
            _prereq_terms(
                (example.expected_output.get("primary") or {}).get("prerequisites", [])
            )
        )
        pred_prereq = set(
            _prereq_terms(
                ((parsed or {}).get("primary") or {}).get("prerequisites", [])
            )
        )
        prereq_recall = (
            len(pred_prereq & gold_prereq) / len(gold_prereq) if gold_prereq else 1.0
        )
        metrics = {
            "strategy_correct": sc,
            "predicted_primary": pred_primary,
            "gold_primary": gold_primary,
            "prerequisite_recall": round(prereq_recall, 4),
        }
        passed = bool(parsed) and sc == 1.0

    elif task == TaskType.COBOL_TO_STRUCTURED:
        gold_paras = set(_paragraph_names(example.expected_output.get("ast")))
        pred_paras = (
            set(_paragraph_names((parsed or {}).get("ast"))) if parsed else set()
        )
        p = prf(pred_paras, gold_paras)
        metrics = {
            "paragraph_prf": p.to_dict(),
            "cfg_summary_present": bool((parsed or {}).get("cfg_summary")),
        }
        passed = bool(parsed) and p.f1 >= rubric.get("min_f1", 0.8)

    elif task == TaskType.COBOL_TO_JAVA:
        gold_java = example.expected_output.get("java", "")
        pred_java = (parsed or {}).get("java", "") if parsed else model_output
        jsc = java_structural_coverage(pred_java, gold_java)
        metrics = {"java_structural": jsc}
        passed = jsc["construct_coverage"] >= rubric.get("min_construct_coverage", 0.7)

    else:  # pragma: no cover - all TaskType handled above
        passed = False
        notes.append(f"no scorer for task {task.value}")

    # -- generic hallucination roll-up -------------------------------
    hall.setdefault("contradicted_by_source", 0)
    is_incorrect = not passed
    hb = hallucination_breakdown(
        predicted_dependencies=set(),
        gold_dependencies=set(),
        predicted_rule_keys=set(),
        gold_rule_keys=set(),
        predicted_risk_keys=set(),
        gold_risk_keys=set(),
        cited_lines=[],
        source_line_count=line_count,
        unsupported_identifier_count=hall.get("unsupported_by_source", 0),
        is_incorrect=is_incorrect,
    )
    hall["incorrect"] = hb["incorrect"]

    return ExampleScore(
        example_id=example.example_id,
        task_type=task.value,
        difficulty=example.difficulty.value,
        parsed_ok=(parsed is not None) if task in _STRUCTURED else True,
        metrics=metrics,
        hallucinations={k: int(v) for k, v in hall.items()},
        attribution=attr,
        passed=bool(passed),
        notes=notes,
    )


# ---------------------------------------------------------------------------


def _answers_match(pred: Any, gold: Any) -> bool:
    if isinstance(gold, dict) and isinstance(pred, dict):
        return all(_answers_match(pred.get(k), v) for k, v in gold.items())
    if isinstance(gold, list) and isinstance(pred, list):
        return sorted(map(str, pred)) == sorted(map(str, gold))
    return str(pred).strip().lower() == str(gold).strip().lower()


def _normalize_citations(cites: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(cites, list):
        return out
    for c in cites:
        if isinstance(c, dict):
            ln = c.get("line")
            terms = c.get("claim_terms") or c.get("terms") or []
            out.append(
                {"line": ln if isinstance(ln, int) else None, "claim_terms": terms}
            )
        elif isinstance(c, int):
            out.append({"line": c, "claim_terms": []})
    return out


def _acknowledges_uncertainty(text: str) -> bool:
    low = (text or "").lower()
    return any(
        p in low
        for p in (
            "cannot be determined",
            "not determinable",
            "insufficient",
            "no evidence",
            "the source does not",
            "not stated",
            "unknown from the source",
        )
    )


def _paragraph_names(ast: Any) -> list[str]:
    if not isinstance(ast, dict):
        return []
    proc = ast.get("procedure_division") or {}
    paras = proc.get("paragraphs") or []
    return [str(p["name"]) for p in paras if isinstance(p, dict) and p.get("name")]


def _prereq_terms(prereqs: Any) -> list[str]:
    if not isinstance(prereqs, list):
        return []
    out = []
    for p in prereqs:
        words = re.findall(r"[a-z]{4,}", str(p).lower())
        out.extend(words[:3])
    return out
