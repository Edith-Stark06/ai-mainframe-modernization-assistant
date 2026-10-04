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

from app.frontend.components import (
    section_header,
    selectable_table,
    stat_row,
    subsection,
)
from app.frontend.design import ui
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
    """The four-layer picture: what goes in, what analyses it, the derived
    components (the only part that varies per file), and what comes out."""
    ui.render(
        ui.layer_diagram(
            [
                ("1. Mainframe", ["COBOL", "JCL", "DB2", "VSAM", "CICS"], "neutral"),
                (
                    "2. Modernization intelligence",
                    [
                        "Parser",
                        "IR",
                        "CFG",
                        "Business rules",
                        "Dependencies",
                        "Risk",
                        "Strategy",
                    ],
                    "neutral",
                ),
                (
                    "3. Target architecture",
                    [str(c.get("name", "Unknown")) for c in components],
                    "accent",
                ),
                ("4. Modern application", ["Java", "REST", "Data", "Tests"], "success"),
            ]
        )
    )


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
        section_header("Architecture", eyebrow="Analyze")
        st.error(error)
        return
    if architecture_response is None:
        section_header("Architecture", eyebrow="Analyze")
        st.info("Run analysis from the sidebar to derive an architecture.")
        return

    if not architecture_response.get("available"):
        section_header("Architecture", eyebrow="Analyze")
        st.markdown(status_pill("NOT AVAILABLE", "UNAVAILABLE"), unsafe_allow_html=True)
        st.caption(
            architecture_response.get("reason") or "Architecture could not be derived."
        )
        return

    arch = architecture_response["architecture"]
    components = arch.get("components", [])

    section_header(
        "Architecture",
        "Derived target components, grouped by layer.",
        eyebrow="Analyze",
    )
    _render_blueprint(components)

    counts = Counter(c["type"] for c in components)
    subsection("Summary", f"{len(components)} component(s) generated.")
    stat_row([(ctype, str(n)) for ctype, n in sorted(counts.items())])

    strategy = arch.get("primary_strategy")
    if strategy:
        st.caption(
            f"Primary strategy: **{strategy['strategy']}** — {strategy['rationale']}"
        )

    if not components:
        st.info("No architecture components were derived for this file.")
        return

    subsection(
        "Component inventory", "Select a row to inspect its evidence and provenance."
    )
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
