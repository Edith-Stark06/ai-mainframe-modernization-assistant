"""
Phase 12 (Stitch redesign) -- Business Rules explorer (#134).

All data comes from the existing ``POST
/workspaces/{id}/modernization/intelligence`` endpoint (Phase 4 business
rules -- deterministic, no LLM). This module only renders; it computes
nothing except two presentation thresholds documented below.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from app.frontend.components import section_header, selectable_table, stat_row

__all__ = ["render_business_rules", "SEVERITY_TO_STATUS"]

#: real backend severity values (risk.severity) -> honest status word.
SEVERITY_TO_STATUS = {
    "HIGH": "FAIL",
    "CRITICAL": "FAIL",
    "MEDIUM": "WARN",
    "LOW": "IDLE",
}

#: presentation threshold only (not a backend field): a rule is shown as
#: "high confidence" once its real ``confidence`` score is >= 0.8.
_HIGH_CONFIDENCE_THRESHOLD = 0.8

#: the real BusinessRuleCategory enum value for error-condition rules
#: (see app/modernization/business_rules/models.py::BusinessRuleCategory).
_ERROR_CONDITION_CATEGORY = "ERROR_CONDITION"


def _rule_location(rule: Dict[str, Any]) -> str:
    locs = rule.get("source_locations") or []
    if not locs:
        return "—"
    loc = locs[0]
    return f"{loc.get('filename', '')}:{loc.get('line', '?')}"


def _rule_inspector(rule: Dict[str, Any], location: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{rule.get('rule_id', '')}** — {rule.get('description', '')}")
        st.markdown(f"Condition: `{rule.get('condition', '')}`")

        actions = rule.get("actions") or []
        if actions:
            st.caption(
                "Actions: "
                + "; ".join(a.get("raw", "") for a in actions if a.get("raw"))
            )

        variables = rule.get("variables") or {}
        meta_cols = st.columns(4)
        meta_cols[0].caption(f"Category: {rule.get('category', '—')}")
        meta_cols[1].caption(f"Paragraph: {rule.get('paragraph', '—')}")
        meta_cols[2].caption(f"Reads: {len(variables.get('reads', []))}")
        meta_cols[3].caption(f"Writes: {len(variables.get('writes', []))}")

        st.caption(f"Source: {location}")
        conf = rule.get("confidence")
        if conf is not None:
            st.caption(f"Confidence: {conf:.0%}")

        if rule.get("evidence"):
            with st.expander("Evidence"):
                for e in rule["evidence"]:
                    st.write(f"- {e}")


def render_business_rules(
    intelligence: Optional[Dict[str, Any]], *, error: Optional[str]
) -> None:
    if error:
        section_header("Business Rules")
        st.error(error)
        return
    if intelligence is None:
        section_header("Business Rules")
        st.info("Run analysis from the sidebar to extract business rules.")
        return

    rules: List[Dict[str, Any]] = intelligence.get("business_rules", [])
    section_header(
        "Business Rules",
        f"{len(rules)} extracted — deterministic extraction, no LLM involved.",
    )
    if not rules:
        st.info("No business rules were extracted from this file.")
        return

    high_confidence = sum(
        1 for r in rules if (r.get("confidence") or 0) >= _HIGH_CONFIDENCE_THRESHOLD
    )
    error_conditions = sum(
        1 for r in rules if r.get("category") == _ERROR_CONDITION_CATEGORY
    )
    stat_row(
        [
            ("Total", str(len(rules))),
            ("High Confidence", str(high_confidence)),
            ("Error Conditions", str(error_conditions)),
        ]
    )

    records = []
    for rule in rules:
        conf = rule.get("confidence")
        records.append(
            {
                "rule_id": rule.get("rule_id", ""),
                "condition": rule.get("condition", ""),
                "paragraph": rule.get("paragraph") or "—",
                "confidence": f"{conf:.0%}" if conf is not None else "—",
                "_rule": rule,
                "_location": _rule_location(rule),
            }
        )

    selected = selectable_table(
        records,
        ["rule_id", "condition", "paragraph", "confidence"],
        key="business_rules_table",
    )
    if selected is None:
        st.caption(
            "Select a rule above to inspect its condition, actions, and evidence."
        )
        return

    _rule_inspector(selected["_rule"], selected["_location"])
