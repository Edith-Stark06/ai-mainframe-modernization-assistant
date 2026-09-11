"""
Phase 12 (Stitch redesign) -- Dependency explorer (#135), graph-first.

Data comes from the existing ``POST /workspaces/{id}/analyze`` endpoint:
the flat ``dependencies`` list (CALL / PERFORM / COPY / VARIABLE_READ /
VARIABLE_WRITE / CONDITION) and the cross-program ``dependency_graph``
(nodes/edges, workspace-resolved CALL/PERFORM/COPY only). Every edge
rendered here is a real edge from that response -- this module never
invents a relationship. Layout uses ``networkx`` (via
``components.render_force_graph``) purely for node positioning; nothing
about the graph's structure is computed here.

"Clicking a node" is implemented as a real, working ``st.dataframe``
row-selection list next to the (non-interactive) SVG graph, since
Streamlit cannot route an SVG click back into Python without a custom
bidirectional component.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import streamlit as st

from app.frontend.components import render_force_graph, section_header, selectable_table

__all__ = ["render_dependencies"]

#: the design's requested filter buckets, mapped onto the real
#: dependency `type` values. CONDITION has no matching bucket here (it
#: still appears under ALL) since none of the five requested categories
#: describes it.
_TYPE_FILTERS: Dict[str, Optional[Set[str]]] = {
    "ALL": None,
    "VARIABLE": {"VARIABLE_READ", "VARIABLE_WRITE"},
    "PARAGRAPH": {"PERFORM"},
    "FILE": {"COPY"},
    "EXTERNAL": {"CALL"},
}


def _dependency_source(dep: Dict[str, Any]) -> str:
    loc = dep.get("source_location")
    if not loc:
        return "—"
    return f"{loc.get('filename', '')}:{loc.get('line', '')}"


def _render_graph_and_inspector(graph: Dict[str, Any]) -> None:
    nodes = [(n["identifier"], n["identifier"]) for n in graph.get("nodes", [])]
    edges = [
        (e["source"], e["target"], e.get("dependency_type", ""))
        for e in graph.get("edges", [])
    ]

    graph_col, inspector_col = st.columns([7, 3], gap="medium")

    with graph_col:
        render_force_graph(
            nodes,
            edges,
            empty_message="No cross-program dependency graph is available for this file.",
        )
        node_records: List[Dict[str, Any]] = [{"Program": n[0]} for n in nodes]
        selected_node = (
            selectable_table(node_records, ["Program"], key="dependency_nodes_table")
            if node_records
            else None
        )

    with inspector_col:
        st.markdown("**Inspector**")
        if not node_records:
            st.caption("No graph nodes to inspect.")
        elif selected_node is None:
            st.caption("Select a program node to inspect its edges.")
        else:
            program = selected_node["Program"]
            st.markdown(f"`{program}`")
            touching = [
                e
                for e in graph.get("edges", [])
                if e.get("source") == program or e.get("target") == program
            ]
            st.caption(f"{len(touching)} edge(s) touch this node.")
            for e in touching:
                outgoing = e.get("source") == program
                arrow = "→" if outgoing else "←"
                other = e.get("target") if outgoing else e.get("source")
                st.caption(f"{arrow} {other} ({e.get('dependency_type', '')})")


def render_dependencies(
    analysis: Optional[Dict[str, Any]], *, error: Optional[str]
) -> None:
    if error:
        section_header("Dependencies")
        st.error(error)
        return
    if analysis is None:
        section_header("Dependencies")
        st.info("Run analysis from the sidebar to explore dependencies.")
        return

    deps: List[Dict[str, Any]] = analysis.get("dependencies", [])
    section_header("Dependencies", f"{len(deps)} reference(s) extracted.")

    graph = analysis.get("dependency_graph") or {}
    _render_graph_and_inspector(graph)

    st.markdown("**All Dependencies**")
    if not deps:
        st.caption("No dependencies were extracted from this file.")
        return

    choice = st.pills(
        "Filter by type",
        options=list(_TYPE_FILTERS.keys()),
        default="ALL",
        required=True,
        key="dep_filter",
        label_visibility="collapsed",
    )
    allowed = _TYPE_FILTERS[choice]
    filtered = [d for d in deps if allowed is None or d.get("type") in allowed]

    st.dataframe(
        [
            {
                "Type": d.get("type"),
                "Target": d.get("target"),
                "Source": _dependency_source(d),
            }
            for d in filtered
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(f"{len(filtered)} of {len(deps)} dependencies shown.")
