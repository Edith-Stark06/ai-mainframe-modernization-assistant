"""
Data Flow Graph Builder (task #stage49).

Purpose:
    Build a :class:`~app.modernization.flow.models.Flow` from the
    ``VARIABLE_READ``/``VARIABLE_WRITE`` dependencies
    :class:`~app.analysis.dependencies.analyzer.DependencyAnalyzer`
    already extracts (task #111) -- which paragraph reads or writes
    which data item. This is the one dependency-type family the
    existing call-graph machinery never turns into a graph:
    :class:`~app.analysis.dependencies.graph.DependencyGraph` (used by
    the ``/analyze`` endpoint's ``dependency_graph`` field) is
    documented to accept any :class:`~app.analysis.dependencies.models.Dependency`,
    but its own ``source`` parameter is the *whole program* name, not
    the owning paragraph -- correct for a CALL/PERFORM call graph
    (where "which program" is the meaningful question) but not for data
    flow (where "which paragraph" is). This module reuses the same
    ``Flow``/``FlowNode``/``FlowEdge`` types
    :func:`~app.modernization.flow.generator.generate_flow` already
    builds the call/control-flow graph from -- and the same
    :data:`~app.modernization.flow.models.EdgeType.READS`/``WRITES``
    values that enum has carried, unused, since task #110 -- rather
    than inventing a third graph representation.

Responsibilities:
    - :func:`build_data_flow_graph` -- one paragraph node per distinct
      ``Dependency.source``, one data-item node per distinct
      ``Dependency.target`` (among ``VARIABLE_READ``/``VARIABLE_WRITE``
      dependencies only), and one edge per dependency
      (``READS``/``WRITES``).

Non-responsibilities:
    - Cross-program data flow (a CALL's ``USING`` parameters passing
      data between programs) -- this graph is scoped to one program's
      own paragraphs and data items, matching
      :class:`~app.analysis.dependencies.graph.DependencyGraph`'s own
      single-program scope.
    - ``CONDITION`` dependencies (a variable an ``IF``/``PERFORM
      UNTIL`` tests) -- a condition test is neither a read that feeds a
      later computation nor a write; including it would blur what
      "reads"/"writes" mean here. Left for a future, separately-scoped
      "control dependency" view if ever needed.

Dependencies:
    - app.analysis.dependencies.models -- Dependency, DependencyType
    - app.analysis.models -- AnalysisResult
    - app.modernization.flow.models -- EdgeType, Flow, FlowEdge, FlowNode, NodeType

Examples:
    Building a data flow graph from an analysis result::

        from app.analysis.dependencies.data_flow import build_data_flow_graph
        from app.analysis.service import AnalysisService

        result = AnalysisService().analyze_file(path)
        flow = build_data_flow_graph(result)
        assert all(n.node_type.name in {"PROCESS", "DATA_ITEM"} for n in flow.nodes)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.analysis.dependencies.models import Dependency, DependencyType
from app.analysis.models import AnalysisResult
from app.modernization.flow.models import EdgeType, Flow, FlowEdge, FlowNode, NodeType

__all__ = ["build_data_flow_graph"]

_DATA_FLOW_TYPES: dict[DependencyType, EdgeType] = {
    DependencyType.VARIABLE_READ: EdgeType.READS,
    DependencyType.VARIABLE_WRITE: EdgeType.WRITES,
}


def build_data_flow_graph(
    analysis_result: AnalysisResult, name: str = "data-flow"
) -> Flow:
    """
    Build the data flow graph for *analysis_result*.

    Args:
        analysis_result: Phase 1-3 output; ``.dependencies`` supplies
            every edge (see the module docstring for which dependency
            types contribute).
        name: The resulting :class:`~app.modernization.flow.models.Flow`'s
            own name.

    Returns:
        A :class:`~app.modernization.flow.models.Flow` with one
        ``PROCESS`` node per paragraph that reads or writes a data item,
        one ``DATA_ITEM`` node per distinct data item, and one
        ``READS``/``WRITES`` edge per dependency. Empty (no nodes, no
        edges) when *analysis_result* has no ``VARIABLE_READ``/
        ``VARIABLE_WRITE`` dependencies at all -- never fabricated.
    """
    relevant: list[Dependency] = [
        dep for dep in analysis_result.dependencies if dep.type in _DATA_FLOW_TYPES
    ]

    nodes: dict[str, FlowNode] = {}
    edges: list[FlowEdge] = []
    seen_edges: set[tuple[str, str, EdgeType]] = set()

    for dep in relevant:
        paragraph = dep.source or "<UNKNOWN>"
        para_id = f"para_{paragraph}"
        var_id = f"var_{dep.target}"

        if para_id not in nodes:
            nodes[para_id] = FlowNode(
                id=para_id, node_type=NodeType.PROCESS, name=paragraph
            )
        if var_id not in nodes:
            nodes[var_id] = FlowNode(
                id=var_id, node_type=NodeType.DATA_ITEM, name=dep.target
            )

        edge_type = _DATA_FLOW_TYPES[dep.type]
        edge_key = (para_id, var_id, edge_type)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append(
            FlowEdge(
                id=f"edge_{len(edges)}",
                source_id=para_id,
                target_id=var_id,
                edge_type=edge_type,
            )
        )

    return Flow(
        id="data-flow-graph",
        name=name,
        nodes=tuple(nodes.values()),
        edges=tuple(edges),
    )
