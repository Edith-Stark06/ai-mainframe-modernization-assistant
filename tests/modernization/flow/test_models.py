import pytest
from dataclasses import FrozenInstanceError

from app.modernization.flow.models import FlowNode, FlowEdge, Flow, NodeType, EdgeType


def test_flow_node_valid() -> None:
    node = FlowNode(
        id="n1",
        node_type=NodeType.PROGRAM,
        name="MAIN-PROG",
        metadata={"key": "val"},
    )
    assert node.id == "n1"
    assert node.node_type == NodeType.PROGRAM
    assert node.name == "MAIN-PROG"
    assert node.metadata == {"key": "val"}


def test_flow_node_invalid_id() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        FlowNode(id="", node_type=NodeType.PROGRAM, name="MAIN")
    with pytest.raises(ValueError, match="cannot be empty"):
        FlowNode(id="   ", node_type=NodeType.PROGRAM, name="MAIN")


def test_flow_node_invalid_name() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        FlowNode(id="n1", node_type=NodeType.PROGRAM, name="")


def test_flow_node_invalid_type() -> None:
    with pytest.raises(ValueError, match="Invalid node_type"):
        FlowNode(id="n1", node_type="PROGRAM", name="MAIN")  # type: ignore


def test_flow_node_immutability() -> None:
    node = FlowNode(
        id="n1",
        node_type=NodeType.PROGRAM,
        name="MAIN",
        metadata={"nested": [1, 2]},
    )
    with pytest.raises(FrozenInstanceError):
        node.name = "OTHER"  # type: ignore

    with pytest.raises(TypeError):
        node.metadata["nested"] = [3]  # type: ignore


def test_flow_edge_valid() -> None:
    edge = FlowEdge(
        id="e1",
        source_id="n1",
        target_id="n2",
        edge_type=EdgeType.CALLS,
        metadata={"order": 1},
    )
    assert edge.id == "e1"
    assert edge.source_id == "n1"
    assert edge.target_id == "n2"
    assert edge.edge_type == EdgeType.CALLS


def test_flow_edge_invalid() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        FlowEdge(id="", source_id="n1", target_id="n2", edge_type=EdgeType.CALLS)
    with pytest.raises(ValueError, match="cannot be empty"):
        FlowEdge(id="e1", source_id="", target_id="n2", edge_type=EdgeType.CALLS)
    with pytest.raises(ValueError, match="Invalid edge_type"):
        FlowEdge(id="e1", source_id="n1", target_id="n2", edge_type="CALLS")  # type: ignore


def test_flow_valid() -> None:
    n1 = FlowNode(id="n1", node_type=NodeType.PROGRAM, name="P1")
    n2 = FlowNode(id="n2", node_type=NodeType.PROGRAM, name="P2")
    e1 = FlowEdge(id="e1", source_id="n1", target_id="n2", edge_type=EdgeType.CALLS)

    flow = Flow(id="f1", name="Flow 1", nodes=[n1, n2], edges=[e1])
    assert flow.id == "f1"
    assert flow.name == "Flow 1"
    assert len(flow.nodes) == 2
    assert len(flow.edges) == 1


def test_flow_empty() -> None:
    flow = Flow(id="f1", name="Empty")
    assert len(flow.nodes) == 0
    assert len(flow.edges) == 0


def test_flow_duplicate_node_ids() -> None:
    n1 = FlowNode(id="n1", node_type=NodeType.PROGRAM, name="P1")
    n2 = FlowNode(id="n1", node_type=NodeType.FILE, name="F1")
    with pytest.raises(ValueError, match="Duplicate node ID"):
        Flow(id="f1", name="Flow 1", nodes=[n1, n2])


def test_flow_duplicate_edge_ids() -> None:
    n1 = FlowNode(id="n1", node_type=NodeType.PROGRAM, name="P1")
    e1 = FlowEdge(id="e1", source_id="n1", target_id="n1", edge_type=EdgeType.CALLS)
    e2 = FlowEdge(id="e1", source_id="n1", target_id="n1", edge_type=EdgeType.READS)
    with pytest.raises(ValueError, match="Duplicate edge ID"):
        Flow(id="f1", name="Flow 1", nodes=[n1], edges=[e1, e2])


def test_flow_dangling_edge() -> None:
    n1 = FlowNode(id="n1", node_type=NodeType.PROGRAM, name="P1")
    e1 = FlowEdge(id="e1", source_id="n1", target_id="n2", edge_type=EdgeType.CALLS)
    with pytest.raises(ValueError, match="Dangling edge: target_id 'n2' not found"):
        Flow(id="f1", name="Flow 1", nodes=[n1], edges=[e1])

    e2 = FlowEdge(id="e2", source_id="n0", target_id="n1", edge_type=EdgeType.CALLS)
    with pytest.raises(ValueError, match="Dangling edge: source_id 'n0' not found"):
        Flow(id="f1", name="Flow 1", nodes=[n1], edges=[e2])


def test_flow_deterministic_ordering() -> None:
    n1 = FlowNode(id="n1", node_type=NodeType.PROGRAM, name="P1")
    n2 = FlowNode(id="n2", node_type=NodeType.PROGRAM, name="P2")
    n3 = FlowNode(id="n3", node_type=NodeType.PROGRAM, name="P3")

    e1 = FlowEdge(id="e1", source_id="n1", target_id="n2", edge_type=EdgeType.CALLS)
    e2 = FlowEdge(id="e2", source_id="n2", target_id="n3", edge_type=EdgeType.CALLS)

    # Supply them out of order
    flow = Flow(id="f1", name="Flow", nodes=[n3, n1, n2], edges=[e2, e1])

    # Should be sorted by id
    assert flow.nodes[0].id == "n1"
    assert flow.nodes[1].id == "n2"
    assert flow.nodes[2].id == "n3"

    assert flow.edges[0].id == "e1"
    assert flow.edges[1].id == "e2"


def test_flow_caller_isolation() -> None:
    nodes = [FlowNode(id="n1", node_type=NodeType.PROGRAM, name="P1")]
    flow = Flow(id="f1", name="F", nodes=nodes)

    # Mutate caller list
    nodes.append(FlowNode(id="n2", node_type=NodeType.PROGRAM, name="P2"))
    assert len(flow.nodes) == 1  # Flow aggregate should remain unaffected


def test_flow_serialization() -> None:
    n1 = FlowNode(id="n1", node_type=NodeType.PROGRAM, name="P1", metadata={"loc": 10})
    n2 = FlowNode(id="n2", node_type=NodeType.FILE, name="F1")
    e1 = FlowEdge(
        id="e1",
        source_id="n1",
        target_id="n2",
        edge_type=EdgeType.WRITES,
        metadata={"mode": "append"},
    )

    flow = Flow(id="f1", name="F", nodes=[n1, n2], edges=[e1], metadata={"tag": "demo"})

    data = flow.to_dict()

    assert data["id"] == "f1"
    assert data["name"] == "F"
    assert data["metadata"]["tag"] == "demo"
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1

    assert data["nodes"][0]["id"] == "n1"
    assert data["nodes"][0]["node_type"] == "PROGRAM"
    assert data["nodes"][0]["metadata"]["loc"] == 10

    assert data["edges"][0]["id"] == "e1"
    assert data["edges"][0]["edge_type"] == "WRITES"
    assert data["edges"][0]["source_id"] == "n1"
    assert data["edges"][0]["target_id"] == "n2"
