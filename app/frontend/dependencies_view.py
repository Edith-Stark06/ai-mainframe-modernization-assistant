"""
Phase 12 (Stitch redesign) -- Dependency explorer (#135), graph-first.

Data comes from the existing ``POST /workspaces/{id}/analyze`` endpoint:
the flat ``dependencies`` list (CALL / PERFORM / COPY / VARIABLE_READ /
VARIABLE_WRITE / CONDITION), the cross-program ``dependency_graph``
(nodes/edges, workspace-resolved CALL/PERFORM/COPY only), and the
per-paragraph ``data_flow_graph`` (task #stage49: which paragraph reads
or writes which data item). Every edge rendered here is a real edge
from that response -- this module never invents a relationship. Layout
uses ``networkx`` (via ``components.render_force_graph``) purely for
node positioning; nothing about the graph's structure is computed here.

"Clicking a node" is implemented as a real, working ``st.dataframe``
row-selection list next to the (non-interactive) SVG graph, since
Streamlit cannot route an SVG click back into Python without a custom
bidirectional component.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

import streamlit as st

from app.frontend.client import BackendAPIError
from app.frontend.components import (
    render_force_graph,
    section_header,
    selectable_table,
    subsection,
)

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


def _render_data_flow_graph(flow: Dict[str, Any]) -> None:
    raw_nodes = flow.get("nodes", [])
    nodes = [
        (
            n["id"],
            n["name"] if n.get("node_type") == "PROCESS" else f"${n['name']}",
        )
        for n in raw_nodes
    ]
    edges = [
        (e["source_id"], e["target_id"], e.get("edge_type", ""))
        for e in flow.get("edges", [])
    ]

    graph_col, inspector_col = st.columns([7, 3], gap="medium")

    with graph_col:
        render_force_graph(
            nodes,
            edges,
            empty_message="No data flow graph is available for this file.",
        )
        if raw_nodes:
            st.caption("Paragraph names in plain text; data items prefixed with '$'.")
        node_records: List[Dict[str, Any]] = [
            {"id": n["id"], "Node": n["name"], "Kind": n.get("node_type", "")}
            for n in raw_nodes
        ]
        selected_node = (
            selectable_table(
                node_records, ["Node", "Kind"], key="data_flow_nodes_table"
            )
            if node_records
            else None
        )

    with inspector_col:
        st.markdown("**Inspector**")
        if not node_records:
            st.caption("No data flow nodes to inspect.")
        elif selected_node is None:
            st.caption("Select a node to inspect its edges.")
        else:
            node_id = selected_node["id"]
            id_to_name = {n["id"]: n["name"] for n in raw_nodes}
            st.markdown(f"`{selected_node['Node']}`")
            touching = [
                e
                for e in flow.get("edges", [])
                if e.get("source_id") == node_id or e.get("target_id") == node_id
            ]
            st.caption(f"{len(touching)} edge(s) touch this node.")
            for e in touching:
                outgoing = e.get("source_id") == node_id
                arrow = "→" if outgoing else "←"
                other_id = e.get("target_id") if outgoing else e.get("source_id")
                other = id_to_name.get(other_id, other_id)
                st.caption(f"{arrow} {other} ({e.get('edge_type', '')})")


_GRAPH_KINDS = {
    "Dependency graph": "dependency",
    "Control flow": "control_flow",
    "Data flow": "data_flow",
}


def _render_dot_export(
    dot_loader: Callable[[str], str], filename: Optional[str]
) -> None:
    """Offer a Graphviz DOT download of one of the analysis graphs.

    The DOT text is produced by the backend (never reconstructed here) and is
    fetched only when asked for, so opening the page costs nothing extra.
    """
    with st.popover("Export graph", icon=":material/download:"):
        label = st.selectbox("Graph", list(_GRAPH_KINDS), key="dot_graph_kind")
        kind = _GRAPH_KINDS[label]
        if st.button("Generate DOT", key="dot_generate"):
            try:
                st.session_state["dot_export"] = (kind, dot_loader(kind))
            except BackendAPIError as exc:
                st.session_state["dot_export"] = None
                st.error(exc.message)
        ready = st.session_state.get("dot_export")
        if ready and ready[0] == kind:
            st.download_button(
                "Download .dot",
                data=ready[1],
                file_name=f"{filename or 'graph'}.{kind}.dot",
                mime="text/vnd.graphviz",
                key="dot_download",
            )
            st.caption("Render with Graphviz: dot -Tsvg file.dot -o graph.svg")


def render_dependencies(
    analysis: Optional[Dict[str, Any]],
    *,
    error: Optional[str],
    dot_loader: Optional[Callable[[str], str]] = None,
    filename: Optional[str] = None,
) -> None:
    if error:
        section_header("Dependencies", eyebrow="Analyze")
        st.error(error)
        return
    if analysis is None:
        section_header("Dependencies", eyebrow="Analyze")
        st.info("Run analysis from the sidebar to explore dependencies.")
        return

    deps: List[Dict[str, Any]] = analysis.get("dependencies", [])
    section_header(
        "Dependencies", f"{len(deps)} reference(s) extracted.", eyebrow="Analyze"
    )
    if dot_loader is not None:
        _render_dot_export(dot_loader, filename)

    graph = analysis.get("dependency_graph") or {}
    _render_graph_and_inspector(graph)

    subsection("Data flow", "Which paragraph reads or writes which data item.")
    data_flow_graph = analysis.get("data_flow_graph") or {}
    _render_data_flow_graph(data_flow_graph)

    subsection("All dependencies")
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
