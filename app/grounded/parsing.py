"""
Parse + VERIFY the model's grounded answer (#123 hallucination defense).

Parsing is lenient (unwrap ```json, tolerate missing keys). Verification
is strict (see :mod:`app.grounded.verification`): a citation to an id
that was never provided is fabricated and dropped; a variable /
paragraph / rule / risk named in the answer that appears nowhere in the
evidence forces the answer to "insufficient context".
"""

from __future__ import annotations

import re

from app.grounded.context import Basis, GroundedContext
from app.grounded.models import ConfidenceBand, GroundedAnswer
from app.grounded.verification import (
    extract_json,
    ungrounded_identifiers,
    verify_evidence,
)

__all__ = ["parse_and_verify"]

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
_ORDER = [
    ConfidenceBand.NONE,
    ConfidenceBand.LOW,
    ConfidenceBand.MODERATE,
    ConfidenceBand.HIGH,
]
_VALUE = {"none": 0.0, "low": 0.3, "moderate": 0.6, "high": 0.9}


def parse_and_verify(text: str, context: GroundedContext) -> GroundedAnswer:
    obj = extract_json(text)
    if obj is None:
        answer_text = (
            text.strip()
            or "The answer cannot be determined from the available evidence."
        )
        cited_raw: list[str] = []
        model_insufficient = True
    else:
        answer_text = str(obj.get("answer", "")).strip()
        raw_ev = obj.get("evidence", [])
        cited_raw = [str(x) for x in raw_ev] if isinstance(raw_ev, list) else []
        model_insufficient = bool(obj.get("insufficient_context", False))

    valid, rejected = verify_evidence(cited_raw, context)
    ungrounded = ungrounded_identifiers(answer_text, context)

    says_cannot = bool(_CANNOT.search(answer_text)) if answer_text else True
    insufficient = model_insufficient or says_cannot or not answer_text

    if ungrounded:
        insufficient = True
        rejected = [*rejected, *ungrounded]
        answer_text = (
            "The answer cannot be determined from the available evidence: it "
            f"refers to {', '.join(ungrounded)}, which is not present in the "
            "analysed program or the supplied evidence."
        )
        valid = []
    if not valid and not insufficient:
        insufficient = True
        answer_text = (
            answer_text
            + "\n\n[grounding] No supplied evidence supports this; it cannot be "
            "determined from the available evidence."
        ).strip()

    if insufficient or not valid:
        band, value = ConfidenceBand.NONE, 0.0
    else:
        det = sum(1 for e in valid if e.basis == Basis.DETERMINISTIC_FACT.value)
        coverage = len(valid) / max(1, min(len(context.by_ref()), 5))
        if det >= 2 and coverage >= 0.6:
            band, value = ConfidenceBand.HIGH, 0.9
        elif det >= 1:
            band, value = ConfidenceBand.MODERATE, 0.6
        else:
            band, value = ConfidenceBand.LOW, 0.3
        declared_key = str((obj or {}).get("confidence", "")).lower()
        if declared_key in _BAND and _ORDER.index(_BAND[declared_key]) < _ORDER.index(
            band
        ):
            band = _BAND[declared_key]
            value = _VALUE[declared_key if declared_key != "medium" else "moderate"]

    basis_breakdown: dict[str, int] = {}
    for e in valid:
        basis_breakdown[e.basis] = basis_breakdown.get(e.basis, 0) + 1

    notes: list[str] = []
    if rejected:
        notes.append(
            f"removed {len(rejected)} fabricated/ungrounded reference(s): {rejected}"
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
