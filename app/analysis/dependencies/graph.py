"""
Dependency Graph Models.

Purpose:
    Provide typed, immutable, in-memory representations of a COBOL
    dependency graph constructed from already extracted Dependency objects.

Responsibilities:
    - Expose ``DependencyGraphNode`` — immutable graph node keyed by identifier.
    - Expose ``DependencyGraphEdge`` — immutable directed edge preserving
      source, target, dependency type, and source location.
    - Expose ``DependencyGraph`` — immutable graph container with
      deterministic construction from a list of Dependency objects.

Non-responsibilities:
    - Dependency extraction (belongs to DependencyAnalyzer).
    - Filesystem resolution or workspace discovery.
    - JCL analysis or COPY support.
    - Graph visualization or API exposure.

Dependencies:
    - app.analysis.dependencies.models — Dependency, DependencyType
    - app.parser.lexer.position — Position
    - Python standard library (dataclasses).

Examples:
    Constructing a graph::

        from app.analysis.dependencies.graph import DependencyGraph
        from app.analysis.dependencies.models import Dependency, DependencyType
        from app.parser.lexer.position import Position

        deps = [
            Dependency(
                type=DependencyType.CALL,
                target="CUSTOMER-SERVICE",
                source_location=Position(line=6, column=13, offset=42, filename="main.cbl"),
            ),
        ]
        graph = DependencyGraph.from_dependencies("MAIN", deps)
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analysis.dependencies.models import Dependency, DependencyType
from app.parser.lexer.position import Position

__all__ = [
    "DependencyGraph",
    "DependencyGraphEdge",
    "DependencyGraphNode",
]


@dataclass(frozen=True)
class DependencyGraphNode:
    """
    Immutable node in a dependency graph.

    Attributes:
        identifier:
            Source or target program identifier.
    """

    identifier: str


@dataclass(frozen=True)
class DependencyGraphEdge:
    """
    Immutable directed edge in a dependency graph.

    Attributes:
        source:
            Identifier of the source program.
        target:
            Identifier of the target program.
        dependency_type:
            Kind of dependency (CALL or PERFORM).
        source_location:
            Source location of the dependency statement, or None if unavailable.
    """

    source: str
    target: str
    dependency_type: DependencyType
    source_location: Position | None


@dataclass(frozen=True)
class DependencyGraph:
    """
    Immutable dependency graph constructed from extracted dependencies.

    Attributes:
        nodes:
            Immutable sequence of graph nodes. The source identifier is
            always the first node.
        edges:
            Immutable sequence of directed edges. Duplicate edges are
            omitted; the first occurrence is preserved.
    """

    nodes: tuple[DependencyGraphNode, ...]
    edges: tuple[DependencyGraphEdge, ...]

    @classmethod
    def from_dependencies(
        cls,
        source: str,
        dependencies: list[Dependency],
    ) -> DependencyGraph:
        """
        Build a dependency graph from a source identifier and extracted dependencies.

        Args:
            source:
                Identifier of the source program. Always becomes the first node.
            dependencies:
                List of extracted Dependency objects.

        Returns:
            A deterministic DependencyGraph with source/target nodes and edges.
        """
        nodes: list[DependencyGraphNode] = [DependencyGraphNode(identifier=source)]
        edges: list[DependencyGraphEdge] = []

        seen_nodes: set[str] = {source}
        seen_edges: set[tuple[str, str, DependencyType]] = set()

        for dep in dependencies:
            target = dep.target

            if target not in seen_nodes:
                seen_nodes.add(target)
                nodes.append(DependencyGraphNode(identifier=target))

            edge_key = (source, target, dep.type)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append(
                    DependencyGraphEdge(
                        source=source,
                        target=target,
                        dependency_type=dep.type,
                        source_location=dep.source_location,
                    )
                )

        return cls(nodes=tuple(nodes), edges=tuple(edges))
