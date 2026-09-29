"""
Graph Export API Router.

Purpose:
    Expose ``GET /workspaces/{workspace_id}/export/graph.dot`` --
    render one of this platform's existing graphs (the cross-program
    dependency graph, the control/call-flow graph, or the data flow
    graph) for a given source file as Graphviz DOT text (the
    "Graphviz" entry in AGENTS.md's Future tech stack). Read-only and
    idempotent, matching the existing search endpoint's GET+query-
    param convention rather than the mutating-looking POST+body shape
    ``/analyze`` uses.

Responsibilities:
    - Resolve *filename* within the workspace (reusing the same
      ``resolve_workspace_source`` guard every other route uses).
    - Run :class:`~app.analysis.service.AnalysisService` and build
      whichever graph *graph* selects, reusing the exact same
      construction each graph already has (``DependencyGraph``,
      ``generate_flow``, ``build_data_flow_graph``) -- this router
      never computes a graph a different endpoint doesn't already.
    - Render it via :func:`app.analysis.graphviz_export.to_dot` and
      return it as ``text/vnd.graphviz``.

Non-responsibilities:
    - Graph construction itself (delegated, per above).
    - Actually invoking Graphviz to render an image -- see
      :mod:`app.analysis.graphviz_export`'s own module docstring for
      why this endpoint stops at DOT source text.

Dependencies:
    - app.analysis.dependencies.data_flow -- build_data_flow_graph
    - app.analysis.dependencies.graph -- DependencyGraph
    - app.analysis.dependencies.models -- STRUCTURAL_DEPENDENCY_TYPES
    - app.analysis.graphviz_export -- to_dot
    - app.analysis.service -- AnalysisService
    - app.api.dependencies.workspace -- resolve_workspace_source
    - app.modernization.flow.generator -- generate_flow
    - app.ingestion.workspace -- WorkspaceManager

Examples:
    ::

        GET /api/v1/workspaces/ws-uuid/export/graph.dot?filename=payroll.cbl&graph=dependency

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.analysis.dependencies.data_flow import build_data_flow_graph
from app.analysis.dependencies.graph import DependencyGraph
from app.analysis.dependencies.models import STRUCTURAL_DEPENDENCY_TYPES
from app.analysis.graphviz_export import to_dot
from app.analysis.service import AnalysisService
from app.api.dependencies.workspace import resolve_workspace_source
from app.core.logging import logger
from app.ingestion.workspace import WorkspaceManager
from app.modernization.flow.generator import generate_flow

router = APIRouter(prefix="/workspaces/{workspace_id}/export", tags=["export"])

GraphKind = Literal["dependency", "control_flow", "data_flow"]


def get_analysis_service() -> AnalysisService:
    return AnalysisService()


def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()


@router.get("/graph.dot", response_class=PlainTextResponse)
def export_graph_dot(
    workspace_id: uuid.UUID,
    filename: str = Query(..., description="Source filename to analyze."),
    graph: GraphKind = Query(
        ...,
        description=(
            "Which graph to export: 'dependency' (cross-program CALL/"
            "PERFORM/COPY graph), 'control_flow' (per-program control/"
            "call-flow graph), or 'data_flow' (paragraph <-> data item "
            "read/write graph)."
        ),
    ),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> PlainTextResponse:
    """
    Export *graph* for *filename* as Graphviz DOT text.

    Args:
        workspace_id: UUID4 of the workspace containing the source file.
        filename: The source filename to analyze.
        graph: Which of this platform's existing graphs to export.
        analysis_service: Injected :class:`AnalysisService`.
        workspace_manager: Injected :class:`WorkspaceManager`.

    Returns:
        A ``text/vnd.graphviz`` response with the rendered DOT source.
        An empty (but valid) graph if the source has no AST (e.g. a
        fatal parse failure) -- never fabricated.
    """
    source_path = resolve_workspace_source(workspace_id, filename, workspace_manager)

    try:
        result = analysis_service.analyze_file(source_path)
    except Exception as e:
        logger.error(f"Analysis failed for {source_path}: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed")

    if result.ast is None:
        return PlainTextResponse(
            to_dot(nodes=[], edges=[], name=graph), media_type="text/vnd.graphviz"
        )

    if graph == "dependency":
        program_name = source_path.stem.upper()
        ident_div = getattr(result.ast, "identification_division", None)
        if ident_div is not None:
            pid_node = getattr(ident_div, "program_id", None)
            if pid_node is not None:
                program_name = pid_node.value.upper()
        structural_dependencies = [
            dep
            for dep in result.dependencies
            if dep.type in STRUCTURAL_DEPENDENCY_TYPES
        ]
        dep_graph = DependencyGraph.from_dependencies(
            program_name, structural_dependencies
        )
        nodes = [(node.identifier, node.identifier) for node in dep_graph.nodes]
        edges = [
            (edge.source, edge.target, edge.dependency_type.name)
            for edge in dep_graph.edges
        ]
    else:
        flow = (
            generate_flow(result)
            if graph == "control_flow"
            else build_data_flow_graph(result)
        )
        nodes = [(n.id, n.name) for n in flow.nodes]
        edges = [(e.source_id, e.target_id, e.edge_type.name) for e in flow.edges]

    dot_text = to_dot(nodes=nodes, edges=edges, name=graph)
    return PlainTextResponse(dot_text, media_type="text/vnd.graphviz")
