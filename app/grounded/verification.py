"""
Shared grounding-verification primitives (#123 / #124).

Both grounded chat and the advisor run the same two checks on model
output:

* :func:`verify_evidence` — a cited evidence id must exist in the context
  that was actually sent; unknown ids are fabricated references.
* :func:`ungrounded_identifiers` — a variable / paragraph / rule / risk
  named in the text must appear somewhere in the evidence; if not, the
  claim is not grounded (regardless of whether it is in the question).
"""

from __future__ import annotations

import re

from app.grounded.context import GroundedContext
from app.grounded.models import EvidenceRef

__all__ = ["verify_evidence", "ungrounded_identifiers", "extract_json"]

_IDENT = re.compile(
    r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b|\bBR-\d+\b|\bRISK-[A-Za-z0-9-]+\b"
)
_STOPWORDS = frozenset(
    {"COBOL", "MOVE", "PERFORM", "DISPLAY", "SECTION", "DIVISION", "END-IF", "STOP-RUN"}
)


def verify_evidence(
    cited: list[str], context: GroundedContext
) -> tuple[list[EvidenceRef], list[str]]:
    by_ref = context.by_ref()
    valid: list[EvidenceRef] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for ref in cited:
        r = str(ref).strip()
        if r in by_ref and r not in seen:
            seen.add(r)
            it = by_ref[r]
            p = it.provenance
            valid.append(
                EvidenceRef(
                    ref=r,
                    basis=it.basis.value,
                    source_id=p.source_id,
                    citation=it.citation(),
                    source_path=p.source_path,
                    line_start=p.line_start,
                    line_end=p.line_end,
                    paragraph=p.paragraph,
                    rule_id=p.rule_id,
                    risk_id=p.risk_id,
                )
            )
        else:
            rejected.append(r)
    return valid, rejected


def ungrounded_identifiers(text: str, context: GroundedContext) -> list[str]:
    if not text:
        return []
    grounded = "\n".join(it.content for it in context.all_items()).upper()
    grounded += (
        "\n"
        + "\n".join(
            f"{it.provenance.paragraph or ''} {it.provenance.rule_id or ''} "
            f"{it.provenance.risk_id or ''} {it.provenance.symbol or ''} "
            f"{it.provenance.java_class or ''} {it.provenance.java_method or ''}"
            for it in context.all_items()
        ).upper()
    )
    return sorted(
        {
            ident
            for ident in _IDENT.findall(text.upper())
            if ident not in _STOPWORDS and ident not in grounded
        }
    )


def extract_json(text: str) -> dict | None:  # type: ignore[type-arg]
    import json

    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = m.group(1) if m else None
    if candidate is None:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            candidate = text[s : e + 1]
    if candidate is None:
        return None
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
