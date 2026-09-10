"""
Phase 12 — Business Rules explorer (#134) and the Risks & Strategy
section reused on the Overview.

All data comes from the existing, previously-unused
``POST /workspaces/{id}/modernization/intelligence`` endpoint (Phase 4
business rules / risks / strategies -- deterministic, no LLM). This
module only renders; it computes nothing.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from app.frontend.theme import status_pill

__all__ = ["render_business_rules", "render_risks_and_strategy"]

_SEVERITY_TO_STATUS = {
    "HIGH": "FAIL",
    "CRITICAL": "FAIL",
    "MEDIUM": "WARN",
    "LOW": "IDLE",
}


def _rule_card(rule: Dict[str, Any]) -> None:
    variables = rule.get("variables") or {}
    actions = rule.get("actions") or []
    location = None
    locs = rule.get("source_locations") or []
    if locs:
        loc = locs[0]
        location = f"{loc.get('filename', '')}:{loc.get('line', '?')}"

    with st.container(border=True):
        head_l, head_r = st.columns([4, 1])
        with head_l:
            st.markdown(
                f"**{rule.get('rule_id', '')}** — {rule.get('description', '')}"
            )
        with head_r:
            conf = rule.get("confidence")
            if conf is not None:
                st.caption(f"confidence {conf:.0%}")

        st.markdown(f"`{rule.get('condition', '')}`")
        if actions:
            st.caption(
                "Actions: "
                + "; ".join(a.get("raw", "") for a in actions if a.get("raw"))
            )

        meta_cols = st.columns(4)
        meta_cols[0].caption(f"Category: {rule.get('category', '—')}")
        meta_cols[1].caption(f"Paragraph: {rule.get('paragraph', '—')}")
        meta_cols[2].caption(f"Reads: {len(variables.get('reads', []))}")
        meta_cols[3].caption(f"Writes: {len(variables.get('writes', []))}")

        if location:
            st.caption(f"Source: {location}")
        if rule.get("evidence"):
            with st.expander("Evidence"):
                for e in rule["evidence"]:
                    st.write(f"- {e}")


def render_business_rules(
    intelligence: Dict[str, Any] | None, *, error: str | None
) -> None:
    st.subheader("Business Rules")
    if error:
        st.error(error)
        return
    if intelligence is None:
        st.info("Run analysis from the sidebar to extract business rules.")
        return

    rules: List[Dict[str, Any]] = intelligence.get("business_rules", [])
    if not rules:
        st.info("No business rules were extracted from this file.")
        return

    st.caption(f"{len(rules)} rule(s) — deterministic extraction, no LLM involved.")
    for rule in rules:
        _rule_card(rule)


def render_risks_and_strategy(intelligence: Dict[str, Any] | None) -> None:
    if intelligence is None:
        return
    risks: List[Dict[str, Any]] = intelligence.get("risks", [])
    strategies: List[Dict[str, Any]] = intelligence.get("strategies", [])

    if not risks and not strategies:
        return

    st.markdown("**Modernization Risks & Strategy**")
    if risks:
        for risk in risks:
            status = _SEVERITY_TO_STATUS.get(
                str(risk.get("severity", "")).upper(), "WARN"
            )
            st.markdown(
                f"{status_pill(risk.get('title', risk.get('risk_id', '')), status)}",
                unsafe_allow_html=True,
            )
            st.caption(risk.get("explanation", ""))
    else:
        st.caption("No risks identified.")

    if strategies:
        primary = next((s for s in strategies if s.get("is_primary")), strategies[0])
        st.caption(
            f"Recommended strategy: **{primary.get('strategy', '—')}** — "
            f"{primary.get('rationale', '')}"
        )
