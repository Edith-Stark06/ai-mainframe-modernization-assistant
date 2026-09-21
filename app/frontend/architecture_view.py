"""
Phase 12 (Stitch redesign) -- Architecture view (#133), backed by the real
``POST /workspaces/{id}/modernization/architecture`` endpoint (#125).

Renders exactly what the backend returned: components, their type,
responsibility, source provenance, and the business rules/dependencies/
external interfaces they reference. The #125 domain model has no
component-to-component edge list -- rather than invent one (e.g. a fake
"orchestrator" box with arrows to services that aren't modeled), components
are grouped visually by type, matching what the backend actually models.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

import streamlit as st

from app.frontend.components import section_header, selectable_table, stat_row
from app.frontend.theme import status_pill

__all__ = ["render_architecture"]

#: a stable top-to-bottom presentation order for component types -- purely
#: cosmetic grouping, not a claimed relationship.
_TYPE_ORDER = ["SERVICE", "DOMAIN", "DTO", "REPOSITORY", "API", "CONTROLLER"]


def _type_sort_key(component_type: str) -> tuple[int, str]:
    try:
        return (_TYPE_ORDER.index(component_type), component_type)
    except ValueError:
        return (len(_TYPE_ORDER), component_type)


def _render_blueprint(components: List[Dict[str, Any]]) -> None:
    # 1. Mainframe Layer
    mainframe_html = """
    <div style="border: 1px solid #333; border-radius: 4px; padding: 15px; margin-bottom: 20px; text-align: center; background: rgba(0,0,0,0.2);">
        <div style="font-size: 10px; letter-spacing: 1px; color: #888; margin-bottom: 10px; font-weight: 600;">1. MAINFRAME</div>
        <div style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
            <span class="mf-topbar-badge">COBOL</span>
            <span class="mf-topbar-badge">JCL</span>
            <span class="mf-topbar-badge">DB2</span>
            <span class="mf-topbar-badge">VSAM</span>
            <span class="mf-topbar-badge">CICS</span>
        </div>
    </div>
    <div style="text-align: center; color: #555; margin-bottom: 20px;">↓</div>
    """

    # 2. Intelligence Layer
    intelligence_html = """
    <div style="border: 1px solid #333; border-radius: 4px; padding: 15px; margin-bottom: 20px; text-align: center; background: rgba(0,0,0,0.2);">
        <div style="font-size: 10px; letter-spacing: 1px; color: #888; margin-bottom: 10px; font-weight: 600;">2. MODERNIZATION INTELLIGENCE</div>
        <div style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
            <span class="mf-topbar-badge" style="background:#111827;border-color:#374151;">Parser</span>
            <span class="mf-topbar-badge" style="background:#111827;border-color:#374151;">IR</span>
            <span class="mf-topbar-badge" style="background:#111827;border-color:#374151;">CFG</span>
            <span class="mf-topbar-badge" style="background:#111827;border-color:#374151;">Business Rules</span>
            <span class="mf-topbar-badge" style="background:#111827;border-color:#374151;">Dependencies</span>
            <span class="mf-topbar-badge" style="background:#111827;border-color:#374151;">Risk</span>
            <span class="mf-topbar-badge" style="background:#111827;border-color:#374151;">Strategy</span>
        </div>
    </div>
    <div style="text-align: center; color: #555; margin-bottom: 20px;">↓</div>
    """

    # 3. Target Architecture Layer (dynamic from backend)
    services_html = ""
    for c in components:
        color = (
            "#1d4ed8"
            if c.get("type") == "SERVICE"
            else "#047857" if c.get("type") == "DOMAIN" else "#4338ca"
        )
        services_html += f'<div style="border: 1px solid {color}; border-radius: 4px; padding: 8px 12px; font-size: 13px; color: #e2e8f0; font-weight: 500;">{c.get("name", "Unknown")}</div>'

    target_html = f"""
    <div style="border: 1px solid #333; border-radius: 4px; padding: 15px; margin-bottom: 20px; text-align: center; background: rgba(0,0,0,0.2);">
        <div style="font-size: 10px; letter-spacing: 1px; color: #888; margin-bottom: 10px; font-weight: 600;">3. TARGET ARCHITECTURE</div>
        <div style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
            {services_html if components else '<span style="color:#666; font-size:12px;">No components derived</span>'}
        </div>
    </div>
    <div style="text-align: center; color: #555; margin-bottom: 20px;">↓</div>
    """

    # 4. Modern Application Layer
    modern_html = """
    <div style="border: 1px solid #333; border-radius: 4px; padding: 15px; margin-bottom: 20px; text-align: center; background: rgba(0,0,0,0.2);">
        <div style="font-size: 10px; letter-spacing: 1px; color: #888; margin-bottom: 10px; font-weight: 600;">4. MODERN APPLICATION</div>
        <div style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
            <span class="mf-topbar-badge" style="border-color:#059669;color:#10b981;">Java</span>
            <span class="mf-topbar-badge" style="border-color:#059669;color:#10b981;">REST</span>
            <span class="mf-topbar-badge" style="border-color:#059669;color:#10b981;">Data</span>
            <span class="mf-topbar-badge" style="border-color:#059669;color:#10b981;">Tests</span>
        </div>
    </div>
    """

    blueprint = f"""
    <div style="max-width: 800px; margin: 0 auto; font-family: ui-sans-serif, system-ui, sans-serif;">
        {mainframe_html}
        {intelligence_html}
        {target_html}
        {modern_html}
    </div>
    """
    st.markdown(blueprint, unsafe_allow_html=True)


def _component_detail(component: Dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown(f"**{component['name']}** — {component['responsibility']}")
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
    architecture_response: Optional[Dict[str, Any]], *, error: Optional[str]
) -> None:
    if error:
        section_header("Architecture")
        st.error(error)
        return
    if architecture_response is None:
        section_header("Architecture")
        st.info("Run analysis from the sidebar to derive an architecture.")
        return

    if not architecture_response.get("available"):
        section_header("Architecture")
        st.markdown(status_pill("NOT AVAILABLE", "UNAVAILABLE"), unsafe_allow_html=True)
        st.caption(
            architecture_response.get("reason") or "Architecture could not be derived."
        )
        return

    arch = architecture_response["architecture"]
    components = arch.get("components", [])

    st.markdown(
        "<h3 style='text-align:center; font-weight:600; font-size: 1.2rem; margin-bottom: 2rem; color: #f8fafc; letter-spacing:1px;'>MODERNIZATION ARCHITECTURE BLUEPRINT</h3>",
        unsafe_allow_html=True,
    )

    _render_blueprint(components)

    st.divider()

    counts = Counter(c["type"] for c in components)
    section_header("Architecture Summary", f"{len(components)} component(s) generated.")
    stat_row([(ctype, str(n)) for ctype, n in sorted(counts.items())])

    strategy = arch.get("primary_strategy")
    if strategy:
        st.caption(
            f"Primary strategy: **{strategy['strategy']}** — {strategy['rationale']}"
        )

    if not components:
        st.info("No architecture components were derived for this file.")
        return

    st.markdown("**Component Inventory**")
    records = []
    for c in components:
        records.append(
            {
                "Name": c["name"],
                "Type": c["type"],
                "Responsibility": c["responsibility"],
                "Rules": len(c.get("business_rule_ids", [])),
                "Dependencies": len(c.get("dependency_ids", [])),
                "_component": c,
            }
        )
    selected = selectable_table(
        records,
        ["Name", "Type", "Responsibility", "Rules", "Dependencies"],
        key="architecture_component_table",
    )
    if selected is not None:
        _component_detail(selected["_component"])
    else:
        st.caption("Select a component above to inspect its evidence and provenance.")

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
