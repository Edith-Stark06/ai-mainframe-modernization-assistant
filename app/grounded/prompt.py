"""
Grounded-chat prompt construction + system contract (#123).

The system prompt states the grounding rules, but grounding is enforced
in code (context validation + citation verification), not by trusting the
model to obey instructions.
"""

from __future__ import annotations

import json

from app.grounded.context import GroundedContext

__all__ = ["PROMPT_VERSION", "SYSTEM_PROMPT", "build_grounded_prompt"]

PROMPT_VERSION = "p8-grounded-v1"

SYSTEM_PROMPT = """\
You are a mainframe-modernization assistant. Answer ONLY from the EVIDENCE \
blocks provided below. Each block has an id like [E1] and a citation.

Rules:
- Use only the supplied evidence. Do not use outside knowledge about COBOL \
programs, variables, paragraphs, business rules, or dependencies.
- Never invent a variable, paragraph, section, business rule, dependency, \
risk, or source line/location. If it is not in the evidence, it does not \
exist for the purpose of your answer.
- Every factual claim about the COBOL program MUST cite one or more \
evidence ids in "evidence".
- Distinguish DETERMINISTIC_FACT evidence (from the parser / analysis) \
from RETRIEVED_KNOWLEDGE evidence. Do not present a recommendation as a fact.
- If the evidence does not let you answer, set "insufficient_context": true \
and say you cannot determine it from the available evidence. Do not guess \
or produce plausible filler.

Respond with ONE JSON object and nothing else:
{
  "answer": "<concise answer, or a statement that it cannot be determined>",
  "evidence": ["E1", "E3"],
  "confidence": "high" | "moderate" | "low" | "none",
  "insufficient_context": true | false
}
"""


def _render_item_block(kind: str, items: list) -> str:  # type: ignore[type-arg]
    if not items:
        return ""
    lines = [f"## {kind}"]
    for it in items:
        lines.append(f"[{it.ref}] ({it.basis.value}) {it.citation()}")
        lines.append(it.content.strip())
        lines.append("")
    return "\n".join(lines)


def build_grounded_prompt(context: GroundedContext) -> str:
    context.validate()  # hard boundary — no anonymous context past here
    parts = [
        SYSTEM_PROMPT,
        "",
        f"# QUESTION\n{context.question.strip()}",
        "",
        "# EVIDENCE",
    ]
    parts.append(
        _render_item_block("SOURCE (DETERMINISTIC_FACT)", context.source_context)
    )
    parts.append(
        _render_item_block("ANALYSIS (DETERMINISTIC_FACT)", context.analysis_context)
    )
    parts.append(
        _render_item_block("RETRIEVED (RETRIEVED_KNOWLEDGE)", context.retrieved_context)
    )
    if context.is_empty:
        parts.append(
            "(no evidence available — you must answer that it cannot be "
            "determined from the available evidence)"
        )
    parts.append("")
    parts.append("# VALID EVIDENCE IDS\n" + json.dumps(sorted(context.by_ref().keys())))
    return "\n".join(p for p in parts if p is not None)
