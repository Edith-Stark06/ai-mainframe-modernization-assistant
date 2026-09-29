"""
Graphviz DOT Export.

Purpose:
    Render any of this platform's existing graphs (the cross-program
    dependency graph, the control/call-flow graph, the data flow
    graph) as Graphviz DOT source text -- the "Graphviz" entry in
    AGENTS.md's Future tech stack. This module only emits DOT *text*;
    it does not shell out to the ``dot`` binary or depend on the
    ``graphviz`` PyPI package, since neither is needed to produce a
    valid, standard DOT file a user can feed into any Graphviz-
    compatible tool (the ``dot``/``neato`` CLI, an online viewer, a
    VS Code/JetBrains Graphviz extension, Gephi, ...). Nothing here
    invents graph structure -- every node and edge comes from the
    caller's already-computed graph.

Responsibilities:
    - :func:`to_dot` -- render already-extracted ``(id, label)`` node
      pairs and ``(source_id, target_id, edge_label)`` edge triples
      (the same shape :func:`app.frontend.components.render_force_graph`
      already consumes) as a directed DOT graph, with node/edge labels
      correctly quoted and escaped.

Non-responsibilities:
    - Actually invoking Graphviz to render an image (PNG/SVG/...) --
      that requires the system ``dot`` binary, which this environment
      cannot assume is installed; emitting the portable DOT *source*
      is the deliverable, and any Graphviz installation can render it
      from there.
    - Graph construction itself (dependency graph, control-flow graph,
      data-flow graph) -- this module only serializes an already-built
      graph's nodes/edges.

Dependencies:
    - Python standard library only.

Examples:
    Exporting a dependency graph's nodes/edges::

        from app.analysis.graphviz_export import to_dot

        dot_text = to_dot(
            nodes=[("MAIN", "MAIN"), ("SUBRTN", "SUBRTN")],
            edges=[("MAIN", "SUBRTN", "CALL")],
            name="dependency_graph",
        )
        assert dot_text.startswith("digraph")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Sequence

__all__ = ["to_dot"]

#: A bare (unquoted) DOT identifier may only contain these characters;
#: anything else forces the quoted-string form. Conservative --
#: COBOL/JCL names routinely contain hyphens, which DOT bare
#: identifiers do not allow, so in practice every node here is quoted.
_BARE_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)


def _quote(text: str) -> str:
    """Render *text* as a DOT quoted string, escaping backslashes and
    double quotes so the emitted DOT is always syntactically valid
    regardless of what the source COBOL/JCL identifier contains."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def to_dot(
    nodes: Sequence[tuple[str, str]],
    edges: Sequence[tuple[str, str, str]],
    *,
    name: str = "G",
) -> str:
    """
    Render *nodes*/*edges* as Graphviz DOT source text.

    Args:
        nodes: Already-extracted ``(id, label)`` pairs -- the same
            shape :func:`app.frontend.components.render_force_graph`
            consumes. *label* is used as the node's display text;
            *id* is used as the DOT node identifier.
        edges: Already-extracted ``(source_id, target_id, edge_label)``
            triples. *edge_label* is rendered on the edge when
            non-empty.
        name: The DOT graph's own name (``digraph <name> {...}``).
            Quoted automatically if it is not a bare DOT identifier.

    Returns:
        A complete, syntactically valid DOT ``digraph`` definition.
        Never fabricates a node or edge not present in the input --
        an empty *nodes* renders an empty (but valid) graph.
    """
    graph_name = name if set(name) <= _BARE_ID_CHARS and name else _quote(name)

    lines = [f"digraph {graph_name} {{"]
    for node_id, label in nodes:
        lines.append(f"  {_quote(node_id)} [label={_quote(label)}];")
    for source_id, target_id, edge_label in edges:
        edge_attrs = f" [label={_quote(edge_label)}]" if edge_label else ""
        lines.append(f"  {_quote(source_id)} -> {_quote(target_id)}{edge_attrs};")
    lines.append("}")
    return "\n".join(lines) + "\n"
