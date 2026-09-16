"""
Unit tests for the Dependency Graph.
"""

from app.analysis.dependencies.graph import (
    DependencyGraph,
    DependencyGraphEdge,
    DependencyGraphNode,
)
from app.analysis.dependencies.models import Dependency, DependencyType
from app.parser.lexer.position import Position


def _pos(
    line: int = 1,
    column: int = 1,
    offset: int = 0,
    filename: str = "test.cbl",
) -> Position:
    return Position(line=line, column=column, offset=offset, filename=filename)


def test_empty_dependency_graph():
    """A graph with no dependencies contains only the source node and no edges."""
    graph = DependencyGraph.from_dependencies("MAIN", [])
    assert len(graph.nodes) == 1
    assert graph.nodes[0].identifier == "MAIN"
    assert len(graph.edges) == 0


def test_single_call_dependency():
    """A single CALL dependency produces source and target nodes and one edge."""
    deps = [
        Dependency(
            type=DependencyType.CALL,
            target="CUSTOMER-SERVICE",
            source_location=_pos(line=6, column=13, offset=42),
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert len(graph.nodes) == 2
    assert graph.nodes[0].identifier == "MAIN"
    assert graph.nodes[1].identifier == "CUSTOMER-SERVICE"
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source == "MAIN"
    assert edge.target == "CUSTOMER-SERVICE"
    assert edge.dependency_type == DependencyType.CALL
    assert edge.source_location == _pos(line=6, column=13, offset=42)


def test_single_perform_dependency():
    """A single PERFORM dependency produces source and target nodes and one edge."""
    deps = [
        Dependency(
            type=DependencyType.PERFORM,
            target="CALCULATE-BONUS",
            source_location=_pos(line=6, column=12, offset=40),
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert len(graph.nodes) == 2
    assert graph.nodes[1].identifier == "CALCULATE-BONUS"
    assert len(graph.edges) == 1
    assert graph.edges[0].dependency_type == DependencyType.PERFORM


def test_multiple_dependencies():
    """Multiple dependencies produce nodes and edges in input order."""
    deps = [
        Dependency(
            type=DependencyType.PERFORM, target="INIT-RTN", source_location=_pos()
        ),
        Dependency(type=DependencyType.CALL, target="SUBPROG", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert len(graph.nodes) == 3
    assert [n.identifier for n in graph.nodes] == ["MAIN", "INIT-RTN", "SUBPROG"]
    assert len(graph.edges) == 2
    assert graph.edges[0].dependency_type == DependencyType.PERFORM
    assert graph.edges[0].target == "INIT-RTN"
    assert graph.edges[1].dependency_type == DependencyType.CALL
    assert graph.edges[1].target == "SUBPROG"


def test_same_target_call_and_perform():
    """CALL and PERFORM to the same target produce distinct edges."""
    deps = [
        Dependency(type=DependencyType.CALL, target="WORK", source_location=_pos()),
        Dependency(type=DependencyType.PERFORM, target="WORK", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 2
    assert graph.edges[0].dependency_type == DependencyType.CALL
    assert graph.edges[1].dependency_type == DependencyType.PERFORM


def test_duplicate_dependency():
    """Duplicate dependencies produce a single edge, preserving first occurrence."""
    deps = [
        Dependency(
            type=DependencyType.CALL,
            target="BONUSMOD",
            source_location=_pos(line=6, column=12, offset=40),
        ),
        Dependency(
            type=DependencyType.CALL,
            target="BONUSMOD",
            source_location=_pos(line=7, column=12, offset=50),
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert graph.edges[0].source_location == _pos(line=6, column=12, offset=40)


def test_source_location_preservation():
    """Source locations are preserved exactly on graph edges."""
    pos = _pos(line=10, column=8, offset=342, filename="WS.cbl")
    deps = [
        Dependency(
            type=DependencyType.CALL,
            target="SUB-PROG",
            source_location=pos,
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert graph.edges[0].source_location == pos
    assert graph.edges[0].source_location.line == 10
    assert graph.edges[0].source_location.column == 8
    assert graph.edges[0].source_location.offset == 342
    assert graph.edges[0].source_location.filename == "WS.cbl"


def test_none_source_location():
    """None source locations are preserved on graph edges."""
    deps = [
        Dependency(
            type=DependencyType.CALL,
            target="UNKNOWN",
            source_location=None,
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert len(graph.edges) == 1
    assert graph.edges[0].source_location is None


def test_deterministic_construction():
    """Repeated construction from identical input produces equivalent graphs."""
    deps1 = [
        Dependency(type=DependencyType.CALL, target="A", source_location=_pos()),
        Dependency(type=DependencyType.PERFORM, target="B", source_location=_pos()),
    ]
    deps2 = [
        Dependency(type=DependencyType.CALL, target="A", source_location=_pos()),
        Dependency(type=DependencyType.PERFORM, target="B", source_location=_pos()),
    ]
    graph1 = DependencyGraph.from_dependencies("MAIN", deps1)
    graph2 = DependencyGraph.from_dependencies("MAIN", deps2)
    assert graph1 == graph2
    assert list(graph1.nodes) == list(graph2.nodes)
    assert list(graph1.edges) == list(graph2.edges)


def test_unknown_target():
    """Unknown targets become graph nodes without validation."""
    deps = [
        Dependency(
            type=DependencyType.CALL,
            target="UNKNOWN-PROGRAM",
            source_location=_pos(),
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert len(graph.nodes) == 2
    assert graph.nodes[1].identifier == "UNKNOWN-PROGRAM"
    assert graph.edges[0].target == "UNKNOWN-PROGRAM"


def test_graph_is_immutable():
    """Graph nodes and edges are immutable tuples."""
    deps = [
        Dependency(type=DependencyType.CALL, target="A", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    assert isinstance(graph.nodes, tuple)
    assert isinstance(graph.edges, tuple)
    assert isinstance(graph.nodes[0], DependencyGraphNode)
    assert isinstance(graph.edges[0], DependencyGraphEdge)


def test_graph_equality():
    """Graphs with identical contents compare as equal."""
    deps = [
        Dependency(type=DependencyType.CALL, target="A", source_location=_pos()),
    ]
    graph1 = DependencyGraph.from_dependencies("MAIN", deps)
    graph2 = DependencyGraph.from_dependencies("MAIN", deps)
    assert graph1 == graph2


def test_node_identifier_preserved():
    """Node identifiers are preserved exactly as provided."""
    deps = [
        Dependency(
            type=DependencyType.PERFORM, target="CALC-RTN", source_location=_pos()
        ),
    ]
    graph = DependencyGraph.from_dependencies("PROG-01", deps)
    assert graph.nodes[0].identifier == "PROG-01"
    assert graph.nodes[1].identifier == "CALC-RTN"
