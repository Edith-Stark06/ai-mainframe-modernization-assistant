"""
Deterministic benchmark metrics (#119 §15-§17).

Pure functions — no randomness, no external calls. Each returns plain
floats / dicts so the report is fully reproducible from a set of model
outputs.

Hallucination taxonomy (§16): a wrong answer is not automatically a
hallucination. We report, separately:

* ``incorrect``              — wrong but grounded (a real identifier, a
  real construct, just the wrong conclusion).
* ``unsupported_by_source``  — a claim with no support anywhere in the
  source or the deterministic analysis.
* ``contradicted_by_source`` — a claim the source/analysis directly
  refutes.
* ``invented_source_location`` — a cited line that does not exist or does
  not contain what the claim says it does.
* ``invented_dependency`` / ``invented_business_rule`` / ``invented_risk``
  — a structured item that appears in the answer but not in the
  deterministic analysis.

Source attribution (§17): a citation is only "precise" when the cited
span actually contains the token(s) the claim is about — the mere
presence of a ``source_locations`` array earns nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "PRF",
    "prf",
    "concept_coverage",
    "unsupported_terms",
    "rule_match_prf",
    "risk_match_prf",
    "strategy_correctness",
    "attribution",
    "java_structural_coverage",
    "hallucination_breakdown",
    "normalize_token",
]


@dataclass(frozen=True)
class PRF:
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> dict[str, float]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def prf(predicted: set[Any], gold: set[Any]) -> PRF:
    if not predicted and not gold:
        return PRF(1.0, 1.0, 1.0)
    tp = len(predicted & gold)
    p = tp / len(predicted) if predicted else 0.0
    r = tp / len(gold) if gold else 0.0
    f = (2 * p * r / (p + r)) if (p + r) else 0.0
    return PRF(p, r, f)


_WORD = re.compile(r"[A-Za-z0-9_\-]+")


def normalize_token(t: str) -> str:
    return t.strip().strip("'\"").upper()


def _tokens(text: str) -> set[str]:
    return {normalize_token(m.group(0)) for m in _WORD.finditer(text or "")}


def concept_coverage(answer_text: str, required_concepts: Iterable[str]) -> float:
    """Fraction of required identifiers/verbs the answer text mentions."""
    req = [normalize_token(c) for c in required_concepts if c and c.strip()]
    if not req:
        return 1.0
    hay = _tokens(answer_text) | {
        normalize_token(w) for w in (answer_text or "").split()
    }
    hit = sum(1 for c in req if c in hay)
    return hit / len(req)


def unsupported_terms(answer_text: str, allowed_terms: Iterable[str]) -> list[str]:
    """
    Identifier-shaped tokens in the answer that are NOT in the source /
    analysis vocabulary. Used to flag invented identifiers.
    """
    allowed = {normalize_token(t) for t in allowed_terms}
    out: list[str] = []
    for tok in sorted(_tokens(answer_text)):
        if len(tok) < 4 or tok.isdigit():
            continue
        # only care about COBOL-identifier-shaped things (contain '-' or
        # look like WS-/an all-caps name)
        if "-" in tok and tok not in allowed:
            out.append(tok)
    return out


def _rule_key(rule: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    cond = " ".join(str(rule.get("condition", "")).split()).upper()
    acts = tuple(
        sorted(
            " ".join(str(a.get("raw", a) if isinstance(a, dict) else a).split()).upper()
            for a in (rule.get("actions", []) or [])
        )
    )
    return (cond, acts)


def rule_match_prf(predicted: list[dict[str, Any]], gold: list[dict[str, Any]]) -> PRF:
    return prf({_rule_key(r) for r in predicted}, {_rule_key(r) for r in gold})


def _risk_key(risk: dict[str, Any]) -> tuple[str, str]:
    return (
        str(risk.get("category", "")).upper(),
        str(risk.get("severity", "")).upper(),
    )


def risk_match_prf(predicted: list[dict[str, Any]], gold: list[dict[str, Any]]) -> PRF:
    return prf({_risk_key(r) for r in predicted}, {_risk_key(r) for r in gold})


def strategy_correctness(
    predicted_primary: str | None, gold_primary: str | None
) -> float:
    if gold_primary is None:
        return 1.0 if predicted_primary is None else 0.0
    return 1.0 if (predicted_primary or "").upper() == gold_primary.upper() else 0.0


@dataclass(frozen=True)
class Attribution:
    precision: float
    recall: float
    invented: int

    def to_dict(self) -> dict[str, float]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "invented": self.invented,
        }


def attribution(
    citations: list[dict[str, Any]],
    source: str,
    gold_locations: list[dict[str, Any]],
) -> Attribution:
    """
    citations: [{line, claim_terms: [..]}] produced by the model.
    A citation is *correct* iff the line exists AND the source line
    contains every claim term. Precision = correct / cited.
    Recall = distinct gold lines covered by a correct citation / gold lines.
    """
    lines = source.splitlines()
    gold_lines = {int(g["line"]) for g in gold_locations if g.get("line")}
    correct_lines: set[int] = set()
    invented = 0
    total = 0
    for c in citations:
        ln = c.get("line")
        if not isinstance(ln, int) or ln < 1 or ln > len(lines):
            invented += 1
            total += 1
            continue
        total += 1
        line_txt = lines[ln - 1].upper()
        terms = [normalize_token(t) for t in c.get("claim_terms", []) if t]
        if all(t in line_txt for t in terms) and terms:
            correct_lines.add(ln)
        elif not terms:
            # a bare line citation with no claim linkage earns nothing
            invented += 0
        else:
            invented += 1
    precision = (
        len(correct_lines) / total if total else (1.0 if not gold_lines else 0.0)
    )
    recall = len(correct_lines & gold_lines) / len(gold_lines) if gold_lines else 1.0
    return Attribution(precision, recall, invented)


_JAVA_CONSTRUCTS = (
    ("class_decl", re.compile(r"\bclass\s+\w+")),
    ("main_method", re.compile(r"public\s+static\s+void\s+main")),
    ("return_stmt", re.compile(r"\breturn\b")),
    ("if_stmt", re.compile(r"\bif\s*\(")),
    ("while_or_for", re.compile(r"\b(while|for)\s*\(")),
    ("method_call", re.compile(r"\w+\s*\([^)]*\)\s*;")),
    ("assignment", re.compile(r"\w+\s*=\s*[^=]")),
    ("println", re.compile(r"System\.out\.println")),
)


def java_structural_coverage(predicted_java: str, gold_java: str) -> dict[str, Any]:
    """
    Fraction of the Java constructs present in the gold output that the
    predicted output also produces. Execution is not attempted here.
    """
    gold_present = {name for name, rx in _JAVA_CONSTRUCTS if rx.search(gold_java or "")}
    pred_present = {
        name for name, rx in _JAVA_CONSTRUCTS if rx.search(predicted_java or "")
    }
    coverage = (
        len(gold_present & pred_present) / len(gold_present)
        if gold_present
        else (1.0 if not pred_present else 0.0)
    )
    return {
        "construct_coverage": round(coverage, 4),
        "gold_constructs": sorted(gold_present),
        "predicted_constructs": sorted(pred_present),
        "missing": sorted(gold_present - pred_present),
        "extra": sorted(pred_present - gold_present),
    }


def hallucination_breakdown(
    *,
    predicted_dependencies: set[str],
    gold_dependencies: set[str],
    predicted_rule_keys: set[Any],
    gold_rule_keys: set[Any],
    predicted_risk_keys: set[Any],
    gold_risk_keys: set[Any],
    cited_lines: list[int],
    source_line_count: int,
    unsupported_identifier_count: int,
    is_incorrect: bool,
) -> dict[str, int]:
    invented_locs = sum(1 for ln in cited_lines if ln < 1 or ln > source_line_count)
    return {
        "incorrect": 1 if (is_incorrect and unsupported_identifier_count == 0) else 0,
        "unsupported_by_source": unsupported_identifier_count,
        "invented_source_location": invented_locs,
        "invented_dependency": len(predicted_dependencies - gold_dependencies),
        "invented_business_rule": len(predicted_rule_keys - gold_rule_keys),
        "invented_risk": len(predicted_risk_keys - gold_risk_keys),
    }
