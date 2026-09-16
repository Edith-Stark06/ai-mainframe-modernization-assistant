"""
Unit tests for the Dependency Analysis Summary.
"""

from app.analysis.dependencies.graph import DependencyGraph
from app.analysis.dependencies.models import Dependency, DependencyType
from app.analysis.dependencies.resolver import DependencyResolution, ResolutionStatus
from app.analysis.dependencies.summary import DependencyAnalysisSummary
from app.parser.lexer.position import Position


def _pos() -> Position:
    return Position(line=1, column=1, offset=0, filename="test.cbl")


def test_empty_graph():
    """An empty graph produces zero counts and an empty mapping."""
    graph = DependencyGraph.from_dependencies("MAIN", [])
    resolutions = []

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 1
    assert summary.edge_count == 0
    assert summary.resolved_target_count == 0
    assert summary.unresolved_target_count == 0
    assert summary.ambiguous_target_count == 0
    assert summary.dependency_counts == {}


def test_single_call():
    """A single CALL dependency produces expected counts."""
    deps = [
        Dependency(type=DependencyType.CALL, target="SUB", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [DependencyResolution(target="SUB", status=ResolutionStatus.RESOLVED)]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 2
    assert summary.edge_count == 1
    assert summary.resolved_target_count == 1
    assert summary.unresolved_target_count == 0
    assert summary.ambiguous_target_count == 0
    assert summary.dependency_counts == {DependencyType.CALL: 1}


def test_single_perform():
    """A single PERFORM dependency produces expected counts."""
    deps = [
        Dependency(type=DependencyType.PERFORM, target="PARA", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [
        DependencyResolution(target="PARA", status=ResolutionStatus.UNRESOLVED)
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 2
    assert summary.edge_count == 1
    assert summary.resolved_target_count == 0
    assert summary.unresolved_target_count == 1
    assert summary.ambiguous_target_count == 0
    assert summary.dependency_counts == {DependencyType.PERFORM: 1}


def test_mixed_call_perform():
    """Mixed CALL and PERFORM dependencies are counted correctly."""
    deps = [
        Dependency(type=DependencyType.CALL, target="SUB1", source_location=_pos()),
        Dependency(type=DependencyType.PERFORM, target="PARA", source_location=_pos()),
        Dependency(type=DependencyType.CALL, target="SUB2", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [
        DependencyResolution(target="SUB1", status=ResolutionStatus.RESOLVED),
        DependencyResolution(target="PARA", status=ResolutionStatus.UNRESOLVED),
        DependencyResolution(target="SUB2", status=ResolutionStatus.AMBIGUOUS),
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 4
    assert summary.edge_count == 3
    assert summary.resolved_target_count == 1
    assert summary.unresolved_target_count == 1
    assert summary.ambiguous_target_count == 1
    assert summary.dependency_counts == {
        DependencyType.CALL: 2,
        DependencyType.PERFORM: 1,
    }


def test_fully_resolved():
    """Fully resolved dependencies produce expected counts."""
    deps = [
        Dependency(type=DependencyType.CALL, target="CUSTOMER", source_location=_pos()),
        Dependency(
            type=DependencyType.PERFORM, target="CALCULATE", source_location=_pos()
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [
        DependencyResolution(target="CUSTOMER", status=ResolutionStatus.RESOLVED),
        DependencyResolution(target="CALCULATE", status=ResolutionStatus.RESOLVED),
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 3
    assert summary.edge_count == 2
    assert summary.resolved_target_count == 2
    assert summary.unresolved_target_count == 0
    assert summary.ambiguous_target_count == 0
    assert summary.dependency_counts == {
        DependencyType.CALL: 1,
        DependencyType.PERFORM: 1,
    }


def test_partially_resolved():
    """Partially resolved dependencies produce expected counts."""
    deps = [
        Dependency(type=DependencyType.CALL, target="CUSTOMER", source_location=_pos()),
        Dependency(type=DependencyType.CALL, target="UNKNOWN", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [
        DependencyResolution(target="CUSTOMER", status=ResolutionStatus.RESOLVED),
        DependencyResolution(target="UNKNOWN", status=ResolutionStatus.UNRESOLVED),
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 3
    assert summary.edge_count == 2
    assert summary.resolved_target_count == 1
    assert summary.unresolved_target_count == 1
    assert summary.ambiguous_target_count == 0
    assert summary.dependency_counts == {
        DependencyType.CALL: 2,
    }


def test_fully_unresolved():
    """Fully unresolved dependencies produce expected counts."""
    deps = [
        Dependency(
            type=DependencyType.CALL, target="UNKNOWN-A", source_location=_pos()
        ),
        Dependency(
            type=DependencyType.PERFORM, target="UNKNOWN-B", source_location=_pos()
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [
        DependencyResolution(target="UNKNOWN-A", status=ResolutionStatus.UNRESOLVED),
        DependencyResolution(target="UNKNOWN-B", status=ResolutionStatus.UNRESOLVED),
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 3
    assert summary.edge_count == 2
    assert summary.resolved_target_count == 0
    assert summary.unresolved_target_count == 2
    assert summary.ambiguous_target_count == 0
    assert summary.dependency_counts == {
        DependencyType.CALL: 1,
        DependencyType.PERFORM: 1,
    }


def test_same_target_with_call_and_perform():
    """Same target with CALL and PERFORM produces two edges but one resolution node."""
    deps = [
        Dependency(type=DependencyType.CALL, target="WORK", source_location=_pos()),
        Dependency(type=DependencyType.PERFORM, target="WORK", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    # 2 edges, but only 1 target node, thus 1 resolution
    resolutions = [
        DependencyResolution(target="WORK", status=ResolutionStatus.RESOLVED)
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 2
    assert summary.edge_count == 2
    assert summary.resolved_target_count == 1
    assert summary.unresolved_target_count == 0
    assert summary.ambiguous_target_count == 0
    assert summary.dependency_counts == {
        DependencyType.CALL: 1,
        DependencyType.PERFORM: 1,
    }


def test_fully_ambiguous():
    """Fully ambiguous dependencies produce expected counts."""
    deps = [
        Dependency(type=DependencyType.CALL, target="CUSTOMER", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [
        DependencyResolution(target="CUSTOMER", status=ResolutionStatus.AMBIGUOUS),
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)

    assert summary.node_count == 2
    assert summary.edge_count == 1
    assert summary.resolved_target_count == 0
    assert summary.unresolved_target_count == 0
    assert summary.ambiguous_target_count == 1
    assert summary.dependency_counts == {
        DependencyType.CALL: 1,
    }


def test_deterministic_summary():
    """The dependency counts mapping is deterministic regardless of construction iteration."""
    deps = [
        Dependency(type=DependencyType.PERFORM, target="A", source_location=_pos()),
        Dependency(type=DependencyType.CALL, target="B", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    resolutions = [
        DependencyResolution(target="A", status=ResolutionStatus.RESOLVED),
        DependencyResolution(target="B", status=ResolutionStatus.RESOLVED),
    ]

    summary = DependencyAnalysisSummary.from_results(graph, resolutions)
    keys = list(summary.dependency_counts.keys())
    assert keys == [DependencyType.CALL, DependencyType.PERFORM]


def test_input_immutability():
    """Summary creation does not mutate the input graph or resolutions."""
    deps = [
        Dependency(type=DependencyType.CALL, target="X", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    original_nodes = list(graph.nodes)
    original_edges = list(graph.edges)

    res = DependencyResolution(target="X", status=ResolutionStatus.RESOLVED)
    resolutions = [res]
    original_resolutions = list(resolutions)

    DependencyAnalysisSummary.from_results(graph, resolutions)

    assert list(graph.nodes) == original_nodes
    assert list(graph.edges) == original_edges
    assert resolutions == original_resolutions
