"""
Dependency Analysis Summary.

Purpose:
    Provides a typed, deterministic summary of the dependency structure
    and workspace resolution state.

Responsibilities:
    - Aggregate graph node and edge counts.
    - Aggregate resolved and unresolved target counts.
    - Count dependencies by their DependencyType.
    - Provide a frozen domain model suitable for reporting or API exposure.

Dependencies:
    - app.analysis.dependencies.graph (DependencyGraph)
    - app.analysis.dependencies.resolver (DependencyResolution, ResolutionStatus)
    - app.analysis.dependencies.models (DependencyType)
"""

from dataclasses import dataclass
from typing import Mapping

from app.analysis.dependencies.graph import DependencyGraph
from app.analysis.dependencies.models import DependencyType
from app.analysis.dependencies.resolver import DependencyResolution, ResolutionStatus

__all__ = ["DependencyAnalysisSummary"]


@dataclass(frozen=True)
class DependencyAnalysisSummary:
    """
    Summary of a program's dependency analysis and workspace resolution.

    Attributes:
        node_count: The total number of nodes in the dependency graph.
        edge_count: The total number of edges in the dependency graph.
        resolved_target_count: The number of dependency targets successfully resolved.
        unresolved_target_count: The number of dependency targets not successfully resolved.
        dependency_counts: Mapping of dependency types to their counts in the graph.
    """

    node_count: int
    edge_count: int
    resolved_target_count: int
    unresolved_target_count: int
    dependency_counts: Mapping[DependencyType, int]

    @classmethod
    def from_results(
        cls,
        graph: DependencyGraph,
        resolutions: list[DependencyResolution],
    ) -> "DependencyAnalysisSummary":
        """
        Create a deterministic summary from a graph and its resolutions.

        Args:
            graph: The immutable DependencyGraph.
            resolutions: The list of DependencyResolution objects from Task-055.

        Returns:
            A new immutable DependencyAnalysisSummary.
        """
        node_count = len(graph.nodes)
        edge_count = len(graph.edges)

        resolved_count = 0
        unresolved_count = 0

        for res in resolutions:
            if res.status == ResolutionStatus.RESOLVED:
                resolved_count += 1
            else:
                unresolved_count += 1

        counts: dict[DependencyType, int] = {}
        for edge in graph.edges:
            counts[edge.dependency_type] = counts.get(edge.dependency_type, 0) + 1

        # Sort keys deterministically to guarantee stable iteration order
        dependency_counts = {
            dtype: counts[dtype]
            for dtype in sorted(counts.keys(), key=lambda t: t.name)
        }

        return cls(
            node_count=node_count,
            edge_count=edge_count,
            resolved_target_count=resolved_count,
            unresolved_target_count=unresolved_count,
            dependency_counts=dependency_counts,
        )
