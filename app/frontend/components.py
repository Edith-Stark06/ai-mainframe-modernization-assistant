"""
Phase 12 (Stitch redesign) -- shared structural rendering primitives.

These are pure presentation helpers built on top of ``theme.py``'s CSS and
``status_pill``: they format and lay out data a caller already fetched from
the backend. None of them fetch, filter, or compute a domain fact -- every
value passed in must already be real. This module exists so every page can
stop hand-rolling its own ``st.container(border=True)`` card and instead
share one compact, consistent visual language (stat strips, pipeline
steppers, status matrices, and click-to-inspect tables).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

import streamlit as st

from app.frontend.theme import status_pill

__all__ = [
    "section_header",
    "stat_row",
    "pipeline_steps",
    "status_matrix",
    "selectable_table",
    "render_force_graph",
]

_STEP_GLYPH = {
    "done": "✓",
    "active": "●",
    "partial": "~",
    "pending": "○",
    "fail": "✗",
}

_GRAPH_CSS = """
<style>
  .mf-force-graph svg { width: 100%; height: auto; }
  .mf-force-node circle { fill: #0d1117; stroke: #2dd4e8; stroke-width: 1.4; }
  .mf-force-node text { fill: #e6edf3; font-size: 10px; text-anchor: middle; }
  .mf-force-edge { stroke: #1c2733; stroke-width: 1.2; fill: none; }
  .mf-force-edge-label { fill: #8b98a5; font-size: 8px; }
</style>
"""


def section_header(
    title: str,
    subtitle: Optional[str] = None,
    *,
    eyebrow: Optional[str] = None,
    eyebrow_accent: Literal["cyan", "violet"] = "cyan",
) -> None:
    """The compact Level-1 page-title block: optional eyebrow, title, and
    an optional one-line muted subtitle -- never a paragraph.
    ``eyebrow_accent="violet"`` is reserved for the AI surface
    (Modernization Chat) -- the one restrained violet accent in the app."""
    eyebrow_cls = (
        "mf-eyebrow-sm mf-ai-accent" if eyebrow_accent == "violet" else "mf-eyebrow-sm"
    )
    eyebrow_html = f'<div class="{eyebrow_cls}">{eyebrow}</div>' if eyebrow else ""
    subtitle_html = f'<div class="mf-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="mf-section-header">{eyebrow_html}'
        f'<div class="mf-section-title">{title}</div>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def stat_row(items: Sequence[Tuple[str, str]]) -> None:
    """A compact horizontal strip of label/value pairs, thin dividers, no
    boxed cards -- the "BUSINESS RULES 6 / DEPENDENCIES 63 / ..." row used
    across Overview, Business Rules, Architecture, Validation, and Chat."""
    if not items:
        return
    cells = "".join(
        f'<div class="mf-stat"><div class="mf-stat-value">{value}</div>'
        f'<div class="mf-stat-label">{label}</div></div>'
        for label, value in items
    )
    st.markdown(f'<div class="mf-statrow">{cells}</div>', unsafe_allow_html=True)


def pipeline_steps(steps: Sequence[Tuple[str, str]]) -> None:
    """The horizontal ANALYZE / UNDERSTAND / TRANSFORM / VALIDATE stepper.
    ``state`` for each step is one of "done" | "active" | "partial" |
    "pending", already derived by the caller from real backend facts."""
    if not steps:
        return
    cells = "".join(
        f'<div class="mf-step mf-step--{state}">'
        f'<span class="mf-step-glyph">{_STEP_GLYPH.get(state, _STEP_GLYPH["pending"])}</span>'
        f"{label}</div>"
        for label, state in steps
    )
    st.markdown(f'<div class="mf-pipeline">{cells}</div>', unsafe_allow_html=True)


def status_matrix(cells: Sequence[Tuple[str, str]]) -> None:
    """A CSS-grid of label + honest status_pill cells, replacing a row of
    bordered ``st.container`` cards (Validation Center, Report checklist)."""
    if not cells:
        return
    rendered = "".join(
        f'<div class="mf-matrix-cell"><div class="mf-matrix-label">{label}</div>'
        f"{status_pill(status, status)}</div>"
        for label, status in cells
    )
    st.markdown(f'<div class="mf-matrix">{rendered}</div>', unsafe_allow_html=True)


def selectable_table(
    records: Sequence[Dict[str, Any]],
    columns: Sequence[str],
    *,
    key: str,
    height: Union[int, Literal["stretch", "content"]] = "content",
) -> Optional[Dict[str, Any]]:
    """Render ``records`` as a compact single-select table and return the
    selected record's *original* dict (not just the displayed columns), or
    ``None`` if nothing is selected.

    This is the one real, working "click a row to open an inspector"
    mechanism available in Streamlit (``st.dataframe`` row selection)
    without building a custom bidirectional component -- used wherever the
    design calls for "clicking a node/rule/issue populates the inspector."
    """
    if not records:
        return None
    display_rows: List[Dict[str, Any]] = [
        {c: r.get(c, "") for c in columns} for r in records
    ]
    event = st.dataframe(
        display_rows,
        hide_index=True,
        width="stretch",
        height=height,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
    )
    selection = event["selection"] if event else None
    selected_rows = list(selection["rows"]) if selection else []
    if not selected_rows:
        return None
    return records[selected_rows[0]]


def render_force_graph(
    nodes: Sequence[Tuple[str, str]],
    edges: Sequence[Tuple[str, str, str]],
    *,
    empty_message: str,
    width: int = 720,
    height: int = 280,
) -> None:
    """A compact force-directed SVG graph shared by Dependencies (the
    cross-program CALL/PERFORM/COPY graph) and Overview (the control-flow
    topology). ``nodes`` are already-fetched ``(id, label)`` pairs,
    ``edges`` are already-fetched ``(source_id, target_id, type_label)``
    triples -- this function only lays them out (via ``networkx.spring_layout``,
    presentation only) and draws them; it never invents a node or an edge.
    """
    if not nodes:
        st.info(empty_message)
        return

    import networkx as nx  # type: ignore[import-untyped]

    # Density-aware sizing: a real graph can have far more nodes than a
    # fixed small canvas can show legibly. Rather than let node circles
    # overlap into an unreadable cluster ("graph overflow"), grow the
    # canvas and shrink nodes/labels as the graph gets denser, and drop
    # per-edge type labels once there are too many to read anyway.
    node_count = len(nodes)
    height = max(height, min(640, 200 + node_count * 6))
    if node_count <= 15:
        radius, font_size, label_len = 26, 10, 12
    elif node_count <= 40:
        radius, font_size, label_len = 17, 8, 9
    else:
        radius, font_size, label_len = 11, 7, 6
    show_edge_labels = node_count <= 25

    labels = dict(nodes)
    graph = nx.DiGraph()
    for node_id, _ in nodes:
        graph.add_node(node_id)
    for source, target, type_label in edges:
        graph.add_edge(source, target, dependency_type=type_label)

    pos = nx.spring_layout(graph, seed=7, k=1.4 / max(len(graph.nodes) ** 0.5, 1))
    xs = [p[0] for p in pos.values()] or [0]
    ys = [p[1] for p in pos.values()] or [0]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    margin = max(radius + 14, 40)

    def scale(x: float, y: float) -> Tuple[float, float]:
        sx = margin + (x - x_min) / max(x_max - x_min, 1e-6) * (width - 2 * margin)
        sy = margin + (y - y_min) / max(y_max - y_min, 1e-6) * (height - 2 * margin)
        return sx, sy

    svg_edges = []
    for source, target, data in graph.edges(data=True):
        x1, y1 = scale(*pos[source])
        x2, y2 = scale(*pos[target])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        label_svg = (
            f'<text class="mf-force-edge-label" x="{mx:.1f}" y="{my:.1f}">'
            f'{data.get("dependency_type", "")}</text>'
            if show_edge_labels
            else ""
        )
        svg_edges.append(
            f'<path class="mf-force-edge" d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}" '
            f'marker-end="url(#mf-force-arrow)"/>{label_svg}'
        )

    svg_nodes = []
    for node in graph.nodes:
        x, y = scale(*pos[node])
        label = str(labels.get(node, node))[:label_len]
        svg_nodes.append(
            f'<g class="mf-force-node"><circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}"/>'
            f'<text x="{x:.1f}" y="{y + 4:.1f}" style="font-size:{font_size}px">'
            f"{label}</text></g>"
        )

    st.markdown(_GRAPH_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="mf-force-graph">
          <svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <marker id="mf-force-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3"
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
        f"{graph.number_of_nodes()} node(s), {graph.number_of_edges()} edge(s) -- "
        "force-directed layout; every edge is exactly what the backend returned."
    )
