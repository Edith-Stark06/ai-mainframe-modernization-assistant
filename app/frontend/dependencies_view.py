"""
Phase 12 — Dependency explorer (#135).

Data comes from the existing, previously-unused
``POST /workspaces/{id}/analyze`` endpoint: the flat ``dependencies``
list (CALL / PERFORM / COPY / VARIABLE_READ / VARIABLE_WRITE /
CONDITION) and the cross-program ``dependency_graph`` (nodes/edges,
workspace-resolved CALL/PERFORM/COPY only). Every edge rendered here is
a real edge from that response -- this module never invents a
relationship. Layout uses ``networkx`` (already a project dependency)
purely for node positioning; nothing about the graph's structure is
computed here.
"""

from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx  # type: ignore[import-untyped]
import streamlit as st

_GRAPH_CSS = """
<style>
  .mf-dep-graph svg { width: 100%; height: auto; }
  .mf-dep-node circle { fill: #0d1117; stroke: #2dd4e8; stroke-width: 1.4; }
  .mf-dep-node text { fill: #e6edf3; font-size: 10px; text-anchor: middle; }
  .mf-dep-edge { stroke: #1c2733; stroke-width: 1.2; fill: none; }
  .mf-dep-edge-label { fill: #8b98a5; font-size: 8px; }
</style>
"""

_TYPE_FILTERS = {
    "All": None,
    "Calls & Performs": {"CALL", "PERFORM"},
    "Copybooks": {"COPY"},
    "Variable Reads": {"VARIABLE_READ"},
    "Variable Writes": {"VARIABLE_WRITE"},
    "Conditions": {"CONDITION"},
}


def _render_program_graph(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
) -> None:
    if not nodes:
        st.info("No cross-program dependency graph is available for this file.")
        return

    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n["identifier"])
    for e in edges:
        g.add_edge(
            e["source"], e["target"], dependency_type=e.get("dependency_type", "")
        )

    pos = nx.spring_layout(g, seed=7, k=1.4 / max(len(g.nodes) ** 0.5, 1))
    width, height = 720, 320
    xs = [p[0] for p in pos.values()] or [0]
    ys = [p[1] for p in pos.values()] or [0]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    def scale(x: float, y: float) -> tuple[float, float]:
        sx = 60 + (x - x_min) / max(x_max - x_min, 1e-6) * (width - 120)
        sy = 40 + (y - y_min) / max(y_max - y_min, 1e-6) * (height - 80)
        return sx, sy

    svg_edges = []
    for source, target, data in g.edges(data=True):
        x1, y1 = scale(*pos[source])
        x2, y2 = scale(*pos[target])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        svg_edges.append(
            f'<path class="mf-dep-edge" d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}" '
            f'marker-end="url(#mf-arrow)"/>'
            f'<text class="mf-dep-edge-label" x="{mx:.1f}" y="{my:.1f}">'
            f'{data.get("dependency_type", "")}</text>'
        )

    svg_nodes = []
    for node in g.nodes:
        x, y = scale(*pos[node])
        svg_nodes.append(
            f'<g class="mf-dep-node"><circle cx="{x:.1f}" cy="{y:.1f}" r="26"/>'
            f'<text x="{x:.1f}" y="{y + 4:.1f}">{node[:12]}</text></g>'
        )

    st.markdown(_GRAPH_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="mf-dep-graph">
          <svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <marker id="mf-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3"
                      orient="auto" markerUnits="strokeWidth">
                <path d="M0,0 L0,6 L7,3 z" fill="#1c2733"/>
              </marker>
            </defs>
            {"".join(svg_edges)}
            {"".join(svg_nodes)}
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"{g.number_of_nodes()} program(s), {g.number_of_edges()} resolved "
        "cross-program edge(s). Node positions are a force-directed layout; "
        "edges are exactly what the backend resolved."
    )


def render_dependencies(analysis: Dict[str, Any] | None, *, error: str | None) -> None:
    st.subheader("Dependencies")
    if error:
        st.error(error)
        return
    if analysis is None:
        st.info("Run analysis from the sidebar to explore dependencies.")
        return

    graph = analysis.get("dependency_graph") or {}
    _render_program_graph(graph.get("nodes", []), graph.get("edges", []))

    st.markdown("**All Dependencies**")
    deps: List[Dict[str, Any]] = analysis.get("dependencies", [])
    if not deps:
        st.caption("No dependencies were extracted from this file.")
        return

    choice = st.selectbox(
        "Filter by type", options=list(_TYPE_FILTERS.keys()), key="dep_filter"
    )
    allowed = _TYPE_FILTERS[choice]
    filtered = [d for d in deps if allowed is None or d.get("type") in allowed]

    st.dataframe(
        [
            {
                "Type": d.get("type"),
                "Target": d.get("target"),
                "Source": (
                    f"{(d.get('source_location') or {}).get('filename', '')}:"
                    f"{(d.get('source_location') or {}).get('line', '')}"
                    if d.get("source_location")
                    else "—"
                ),
            }
            for d in filtered
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(f"{len(filtered)} of {len(deps)} dependencies shown.")
