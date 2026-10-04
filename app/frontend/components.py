"""
Shared Streamlit-facing components.

Purpose:
    Thin wrappers that put the design system's primitives
    (:mod:`app.frontend.design.ui`) on the page, plus the two components that
    need Streamlit itself: the selectable table and the network graph. None of
    them fetches, filters or computes a domain fact -- every value passed in
    must already be real.

Responsibilities:
    - Page / section headings: :func:`section_header`, :func:`subsection`.
    - Figures: :func:`stat_row`, :func:`pipeline_steps`, :func:`status_matrix`.
    - :func:`selectable_table` -- a single-row-select table that returns the
      selected record.
    - :func:`render_force_graph` -- the dependency / control-flow network.

Dependencies:
    - streamlit, networkx (layout only), app.frontend.design.ui

Examples:
    ::

        section_header("Business Rules", "10 extracted", eyebrow="Analyze")
        stat_row([("Rules", "10"), ("Coverage", "99%")])

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

import streamlit as st

from app.frontend.design import ui

__all__ = [
    "pipeline_steps",
    "render_force_graph",
    "section_header",
    "selectable_table",
    "stat_row",
    "status_matrix",
    "subsection",
]

_STATE_ALIAS = {"active": "partial"}


def section_header(
    title: str,
    subtitle: Optional[str] = None,
    *,
    eyebrow: Optional[str] = None,
    eyebrow_accent: Literal["cyan", "violet"] = "cyan",
) -> None:
    """The page title block: optional eyebrow, title, one muted line.

    ``eyebrow_accent`` is accepted for backward compatibility and ignored: the
    design system has a single accent.
    """
    ui.render(ui.page_header(title, subtitle, eyebrow=eyebrow))


def subsection(title: str, hint: Optional[str] = None) -> None:
    """A heading inside a page, with an optional one-line hint."""
    ui.render(
        f'<div class="ds-section"><h2 class="ds-h2">{ui.esc(title)}</h2>'
        + (f'<p class="ds-hint">{ui.esc(hint)}</p>' if hint else "")
        + "</div>"
    )


def stat_row(items: Sequence[Tuple[str, str]]) -> None:
    """A responsive grid of label / value tiles."""
    if not items:
        return
    ui.render(ui.kpi_grid([{"label": label, "value": value} for label, value in items]))


def pipeline_steps(steps: Sequence[Tuple[str, str]]) -> None:
    """The ANALYZE / UNDERSTAND / TRANSFORM / VALIDATE stepper from
    ``(label, state)`` pairs already derived from real backend facts."""
    if not steps:
        return
    ui.render(
        ui.stepper(
            [
                {
                    "name": label,
                    "state": _STATE_ALIAS.get(state, state),
                    "metric": "",
                    "detail": "",
                }
                for label, state in steps
            ]
        )
    )


def status_matrix(cells: Sequence[Tuple[str, str]]) -> None:
    """One chip per ``(label, status)``: the label and an honest status badge."""
    if not cells:
        return
    ui.render(
        ui.stage_grid([{"stage": label, "status": status} for label, status in cells])
    )


def selectable_table(
    records: Sequence[Dict[str, Any]],
    columns: Sequence[str],
    *,
    key: str,
    height: Union[int, Literal["stretch", "content"]] = "content",
    column_config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Render *records* as a single-select table; return the selected record.

    The returned value is the record's *original* dict (not only the shown
    columns), or ``None`` when nothing is selected. This is the working "click a
    row to open the inspector" mechanism Streamlit offers without a custom
    component.

    Args:
        records: Source rows.
        columns: Which keys to display, in order.
        key: Streamlit widget key.
        height: Table height (``"content"`` fits the rows).
        column_config: Optional ``st.column_config`` per column (widths,
            progress bars, formatting).
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
        column_config=column_config,
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
    height: int = 320,
    caption: bool = True,
) -> None:
    """A force-directed SVG graph for dependencies and control flow.

    ``nodes`` are already-fetched ``(id, label)`` pairs and ``edges``
    ``(source_id, target_id, type_label)`` triples; this lays them out
    (``networkx.spring_layout``, presentation only) and draws them. It never
    invents a node or an edge. The canvas grows and the nodes shrink as the
    graph gets denser, and edge labels are dropped once there are too many to
    read.
    """
    if not nodes:
        ui.render(ui.empty_state("search", "Nothing to draw", empty_message))
        return

    import networkx as nx  # type: ignore[import-untyped]

    node_count = len(nodes)
    height = max(height, min(680, 220 + node_count * 6))
    if node_count <= 15:
        radius, font_size, label_len = 27, 10, 12
    elif node_count <= 40:
        radius, font_size, label_len = 18, 8, 9
    else:
        radius, font_size, label_len = 12, 7, 6
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
    x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)
    margin = max(radius + 16, 44)

    def scale(x: float, y: float) -> Tuple[float, float]:
        sx = margin + (x - x_min) / max(x_max - x_min, 1e-6) * (width - 2 * margin)
        sy = margin + (y - y_min) / max(y_max - y_min, 1e-6) * (height - 2 * margin)
        return sx, sy

    svg_edges: List[str] = []
    for source, target, data in graph.edges(data=True):
        x1, y1 = scale(*pos[source])
        x2, y2 = scale(*pos[target])
        label = (
            f'<text class="edge-label" x="{(x1 + x2) / 2:.1f}" y="{(y1 + y2) / 2:.1f}">'
            f"{ui.esc(data.get('dependency_type', ''))}</text>"
            if show_edge_labels
            else ""
        )
        svg_edges.append(
            f'<path class="edge" d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}" '
            f'marker-end="url(#ds-arrow)"/>{label}'
        )

    svg_nodes: List[str] = []
    for node in graph.nodes:
        x, y = scale(*pos[node])
        full = str(labels.get(node, node))
        svg_nodes.append(
            f'<g class="node"><title>{ui.esc(full)}</title><circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}"/>'
            f'<text x="{x:.1f}" y="{y + 3.5:.1f}" style="font-size:{font_size}px">{ui.esc(full[:label_len])}</text></g>'
        )

    n_nodes, n_edges = graph.number_of_nodes(), graph.number_of_edges()
    summary = f"{n_nodes} node{'s' if n_nodes != 1 else ''} and {n_edges} edge{'s' if n_edges != 1 else ''}"
    ui.render(
        f'<div class="ds-graph"><svg viewBox="0 0 {width} {height}" role="img" aria-label="Network graph: {summary}" '
        'xmlns="http://www.w3.org/2000/svg"><defs><marker id="ds-arrow" markerWidth="8" markerHeight="8" '
        'refX="7" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L7,3 z" '
        'fill="var(--c-hairline-strong)"/></marker></defs>'
        f'{"".join(svg_edges)}{"".join(svg_nodes)}</svg></div>'
    )
    if caption:
        st.caption(f"{summary}. Every edge is exactly what the backend returned.")
