"""
Parse + VERIFY the model's grounded answer (#123 hallucination defense).

Parsing is lenient (unwrap ```json, tolerate missing keys). Verification
is strict: every cited evidence id must exist in the context that was
sent. A citation to an id that was never provided is a fabricated
reference — it is dropped and recorded in ``rejected_claims``. If a
factual answer ends up with zero valid evidence, the answer is forced to
"insufficient context".
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.grounded.context import Basis, GroundedContext
from app.grounded.models import ConfidenceBand, EvidenceRef, GroundedAnswer

__all__ = ["parse_and_verify"]

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
#: COBOL-style identifiers, rule/risk ids, java members mentioned in an answer
_IDENT = re.compile(
    r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b|\bBR-\d+\b|\bRISK-[A-Za-z0-9-]+\b"
)
_STOPWORDS = frozenset(
    {"COBOL", "MOVE", "PERFORM", "DISPLAY", "SECTION", "DIVISION", "END-IF"}
)
_CANNOT = re.compile(
    r"cannot (?:be )?determine|not (?:be )?determined|insufficient|"
    r"no (?:supporting )?evidence|not supported by",
    re.IGNORECASE,
)
_BAND = {
    "high": ConfidenceBand.HIGH,
    "moderate": ConfidenceBand.MODERATE,
    "medium": ConfidenceBand.MODERATE,
    "low": ConfidenceBand.LOW,
    "none": ConfidenceBand.NONE,
}


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = _JSON_BLOCK.search(text)
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


def parse_and_verify(text: str, context: GroundedContext) -> GroundedAnswer:
    by_ref = context.by_ref()
    obj = _extract_json(text)

    if obj is None:
        answer_text = (
            text.strip()
            or "The answer cannot be determined from the available evidence."
        )
        cited_raw: list[str] = []
        model_insufficient = True  # unparseable -> treat as uncertain
    else:
        answer_text = str(obj.get("answer", "")).strip()
        raw_ev = obj.get("evidence", [])
        cited_raw = [str(x).strip() for x in raw_ev] if isinstance(raw_ev, list) else []
        model_insufficient = bool(obj.get("insufficient_context", False))

    # --- verify every citation against the real context -----------------
    valid: list[EvidenceRef] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for ref in cited_raw:
        if ref in by_ref and ref not in seen:
            seen.add(ref)
            it = by_ref[ref]
            p = it.provenance
            valid.append(
                EvidenceRef(
                    ref=ref,
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
            rejected.append(ref)

    # --- identifier grounding: an answer must not name a variable /
    #     paragraph / rule / risk that appears nowhere in the evidence ---
    grounded_text = "\n".join(it.content for it in context.all_items()).upper()
    grounded_text += (
        "\n"
        + "\n".join(
            f"{it.provenance.paragraph or ''} {it.provenance.rule_id or ''} "
            f"{it.provenance.risk_id or ''} {it.provenance.symbol or ''}"
            for it in context.all_items()
        ).upper()
    )
    # NB: an identifier being present in the *question* does not make it
    # grounded — "what is the value of XYZ?" for a nonexistent XYZ must
    # still resolve to "cannot be determined".
    ungrounded_ids = sorted(
        {
            ident
            for ident in _IDENT.findall(answer_text.upper())
            if ident not in _STOPWORDS and ident not in grounded_text
        }
    )

    # --- decide sufficiency -------------------------------------------
    says_cannot = bool(_CANNOT.search(answer_text)) if answer_text else True
    insufficient = model_insufficient or says_cannot or not answer_text
    if ungrounded_ids:
        insufficient = True
        rejected.extend(ungrounded_ids)
        answer_text = (
            "The answer cannot be determined from the available evidence: it "
            f"refers to {', '.join(ungrounded_ids)}, which is not present in "
            "the analysed program or the supplied evidence."
        )
        valid = []
    if not valid and not insufficient:
        # a factual-looking answer with no grounded evidence -> not allowed
        insufficient = True
        answer_text = (
            answer_text
            + "\n\n[grounding] No supplied evidence supports this; it cannot be "
            "determined from the available evidence."
        ).strip()

    # --- confidence band (evidence coverage, not probability) ---------
    n_ctx = len(by_ref)
    if insufficient or not valid:
        band, value = ConfidenceBand.NONE, 0.0
    else:
        det = sum(1 for e in valid if e.basis == Basis.DETERMINISTIC_FACT.value)
        coverage = len(valid) / max(1, min(n_ctx, 5))
        if det >= 2 and coverage >= 0.6:
            band, value = ConfidenceBand.HIGH, 0.9
        elif det >= 1:
            band, value = ConfidenceBand.MODERATE, 0.6
        else:
            band, value = ConfidenceBand.LOW, 0.3
        if obj is not None and str(obj.get("confidence", "")).lower() in _BAND:
            declared = _BAND[str(obj["confidence"]).lower()]
            # never let the model claim MORE than the evidence supports
            order = [
                ConfidenceBand.NONE,
                ConfidenceBand.LOW,
                ConfidenceBand.MODERATE,
                ConfidenceBand.HIGH,
            ]
            if order.index(declared) < order.index(band):
                band = declared
                value = {"none": 0.0, "low": 0.3, "moderate": 0.6, "high": 0.9}[
                    declared.value.split("_")[0]
                ]

    basis_breakdown: dict[str, int] = {}
    for e in valid:
        basis_breakdown[e.basis] = basis_breakdown.get(e.basis, 0) + 1

    notes: list[str] = []
    if rejected:
        notes.append(
            f"{len(rejected)} fabricated / ungrounded reference(s) removed: {rejected}"
        )
    if ungrounded_ids:
        notes.append(
            "answer named identifiers absent from the program/evidence: "
            + ", ".join(ungrounded_ids)
        )
    if context.is_empty:
        notes.append("no evidence was available for this question")

    return GroundedAnswer(
        answer=answer_text
        or "The answer cannot be determined from the available evidence.",
        evidence=tuple(valid),
        confidence=band,
        confidence_value=value,
        insufficient_context=insufficient,
        rejected_claims=tuple(rejected),
        basis_breakdown=basis_breakdown,
        notes=tuple(notes),
    )
