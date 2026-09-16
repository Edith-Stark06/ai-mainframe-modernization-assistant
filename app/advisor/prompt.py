"""Advisor prompt (#124) — same grounding contract as #123, advisor output shape."""

from __future__ import annotations

import json

from app.grounded.context import GroundedContext

__all__ = ["ADVISOR_PROMPT_VERSION", "build_advisor_prompt"]

ADVISOR_PROMPT_VERSION = "p8-advisor-v1"

_SYSTEM = """\
You are an AI modernization advisor. You are given DETERMINISTIC FACTS and \
EVIDENCE from a deterministic COBOL analyzer. The facts are already correct \
— do not re-derive dependencies, rules, risks, or structure.

Your job:
- "conclusion": a grounded statement of what the evidence shows for this \
question. Every factual claim must cite evidence ids. Never invent a \
variable, paragraph, rule, risk, dependency, or source location.
- "recommendation": your modernization advice. This is an AI recommendation, \
not a fact. It may reason beyond the evidence but must not contradict it or \
assert nonexistent program elements.
- If the evidence is insufficient for a grounded conclusion, set \
"insufficient_context": true and say so plainly.

Respond with ONE JSON object only:
{
  "conclusion": "...",
  "recommendation": "...",
  "evidence": ["E1", "E2"],
  "confidence": "high" | "moderate" | "low" | "none",
  "insufficient_context": true | false
}
"""


def _block(title: str, items: list) -> str:  # type: ignore[type-arg]
    if not items:
        return ""
    out = [f"## {title}"]
    for it in items:
        out.append(f"[{it.ref}] ({it.basis.value}) {it.citation()}")
        out.append(it.content.strip())
        out.append("")
    return "\n".join(out)


def build_advisor_prompt(operation: str, context: GroundedContext) -> str:
    context.validate()
    parts = [
        _SYSTEM,
        "",
        f"# OPERATION\n{operation}",
        f"# QUESTION\n{context.question.strip()}",
        "",
        "# EVIDENCE",
        _block("SOURCE (DETERMINISTIC_FACT)", context.source_context),
        _block("ANALYSIS (DETERMINISTIC_FACT)", context.analysis_context),
        _block("RETRIEVED (RETRIEVED_KNOWLEDGE)", context.retrieved_context),
        "",
        "# VALID EVIDENCE IDS\n" + json.dumps(sorted(context.by_ref().keys())),
    ]
    if context.is_empty:
        parts.insert(
            -1,
            "(no evidence — the conclusion must be that it cannot be "
            "determined from the available evidence)",
        )
    return "\n".join(p for p in parts if p)
