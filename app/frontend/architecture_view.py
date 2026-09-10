"""
Phase 12 -- Architecture view (#133), backed by the real
``POST /workspaces/{id}/modernization/architecture`` endpoint (#125).

Renders exactly what the backend returned: components, their type,
responsibility, source provenance, and the business rules/dependencies/
external interfaces they reference. The #125 domain model has no
component-to-component edge list -- rather than invent one, components
are shown as evidence cards grouped by type, matching what the backend
actually models.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict

import streamlit as st

from app.frontend.theme import status_pill

__all__ = ["render_architecture"]


def _component_card(component: Dict[str, Any]) -> None:
    with st.container(border=True):
        head_l, head_r = st.columns([4, 1])
        with head_l:
            st.markdown(f"**{component['name']}** — {component['responsibility']}")
        with head_r:
            st.caption(component["type"])

        meta_cols = st.columns(3)
        meta_cols[0].caption(
            f"Business rules: {len(component.get('business_rule_ids', []))}"
        )
        meta_cols[1].caption(
            f"Dependencies: {len(component.get('dependency_ids', []))}"
        )
        meta_cols[2].caption(
            f"External interfaces: {len(component.get('external_interface_ids', []))}"
        )

        refs = component.get("source_refs", [])
        if refs:
            locations = ", ".join(
                f"{r.get('source_path') or ''}"
                + (f":{r['line_start']}" if r.get("line_start") else "")
                for r in refs
            )
            st.caption(f"Source: {locations}")

        if component.get("evidence"):
            with st.expander("Evidence"):
                for e in component["evidence"]:
                    st.write(f"- **{e.get('kind', '')}**: {e.get('detail', '')}")


def render_architecture(
    architecture_response: Dict[str, Any] | None, *, error: str | None
) -> None:
    st.subheader("Architecture")
    if error:
        st.error(error)
        return
    if architecture_response is None:
        st.info("Run analysis from the sidebar to derive an architecture.")
        return

    if not architecture_response.get("available"):
        st.markdown(status_pill("NOT AVAILABLE", "UNAVAILABLE"), unsafe_allow_html=True)
        st.caption(
            architecture_response.get("reason") or "Architecture could not be derived."
        )
        return

    arch = architecture_response["architecture"]
    components = arch.get("components", [])

    counts = Counter(c["type"] for c in components)
    if counts:
        cols = st.columns(len(counts))
        for col, (ctype, n) in zip(cols, sorted(counts.items())):
            col.metric(ctype, n)

    strategy = arch.get("primary_strategy")
    if strategy:
        st.caption(
            f"Primary strategy: **{strategy['strategy']}** — {strategy['rationale']}"
        )

    if not components:
        st.info("No architecture components were derived for this file.")
    for component in components:
        _component_card(component)

    unsupported = arch.get("unsupported_behaviors", [])
    if unsupported:
        with st.expander(f"⚠ {len(unsupported)} unsupported construct(s)"):
            for u in unsupported:
                st.write(f"- **{u['construct_name']}**: {u['explanation']}")

    assumptions = arch.get("assumptions", [])
    if assumptions:
        with st.expander(f"{len(assumptions)} assumption(s)"):
            for a in assumptions:
                st.write(f"- {a['statement']} — _{a['reason']}_")
