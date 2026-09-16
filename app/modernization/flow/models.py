"""
Flow Domain Models.

Defines the stable, immutable, deterministic representation of nodes and relationships in an application flow.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Mapping, Sequence

from app.rag.models import _freeze_metadata, _to_json_compatible


class NodeType(Enum):
    """Supported categories for flow nodes."""

    PROGRAM = auto()
    FILE = auto()
    DATABASE = auto()
    TRANSACTION = auto()
    DECISION = auto()
    PROCESS = auto()
    EXTERNAL = auto()


class EdgeType(Enum):
    """Supported categories for flow edges."""

    CALLS = auto()
    READS = auto()
    WRITES = auto()
    FLOWS_TO = auto()
    DEPENDS_ON = auto()
    INVOKES = auto()

    # Added by task #110 (Control Flow Graph) to represent real COBOL
    # execution flow rather than only call relationships between whole
    # functions. Kept as new members alongside the existing ones rather
    # than repurposing FLOWS_TO/CALLS, since a consumer that only knows
    # the pre-#110 edge types can keep treating any of these as "some
    # kind of flow" without misreading e.g. a false branch as a call.
    TRUE_BRANCH = auto()  # IF condition -> first statement of the THEN branch
    FALSE_BRANCH = auto()  # IF condition -> first statement of the ELSE branch,
    #                        or directly to the join point when there is no ELSE
    LOOP_BODY = auto()  # PERFORM UNTIL condition -> first statement of the body
    LOOP_BACK = auto()  # last statement of a loop body -> back to its condition
    LOOP_EXIT = auto()  # loop condition -> the statement after the loop
    PERFORMS = auto()  # PERFORM <paragraph> -> the target paragraph's entry
    GOES_TO = auto()  # GO TO <paragraph> -> the target paragraph's entry
    FALLTHROUGH = auto()  # a paragraph with no terminal statement -> the next
    #                        paragraph in source order (COBOL's implicit fall-
    #                        through when a paragraph is not exited via GOBACK/
    #                        STOP RUN/GO TO)


@dataclass(frozen=True)
class FlowNode:
    """
    An immutable domain representation of a unit in an application flow.
    """

    id: str
    node_type: NodeType
    name: str
    source_reference: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("FlowNode id cannot be empty or whitespace-only.")
        if not self.name or not self.name.strip():
            raise ValueError("FlowNode name cannot be empty or whitespace-only.")
        if not isinstance(self.node_type, NodeType):
            raise ValueError(f"Invalid node_type: {self.node_type}")

        # Bypass frozen dataclass to set the frozen metadata safely
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Serializes the node to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "node_type": self.node_type.name,
            "name": self.name,
            "source_reference": self.source_reference,
            "metadata": _to_json_compatible(self.metadata),
        }


@dataclass(frozen=True)
class FlowEdge:
    """
    An immutable domain representation of a directed relationship between two flow nodes.
    """

    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("FlowEdge id cannot be empty or whitespace-only.")
        if not self.source_id or not self.source_id.strip():
            raise ValueError("FlowEdge source_id cannot be empty or whitespace-only.")
        if not self.target_id or not self.target_id.strip():
            raise ValueError("FlowEdge target_id cannot be empty or whitespace-only.")
        if not isinstance(self.edge_type, EdgeType):
            raise ValueError(f"Invalid edge_type: {self.edge_type}")

        # Bypass frozen dataclass to set the frozen metadata safely
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Serializes the edge to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.name,
            "metadata": _to_json_compatible(self.metadata),
        }


@dataclass(frozen=True)
class Flow:
    """
    An immutable domain representation of an application execution flow.
    """

    id: str
    name: str
    nodes: Sequence[FlowNode] = field(default_factory=tuple)
    edges: Sequence[FlowEdge] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("Flow id cannot be empty or whitespace-only.")
        if not self.name or not self.name.strip():
            raise ValueError("Flow name cannot be empty or whitespace-only.")

        # Validate nodes uniqueness and prepare deterministic sorting
        seen_node_ids: set[str] = set()
        node_list: list[FlowNode] = []
        for node in self.nodes:
            if not isinstance(node, FlowNode):
                raise ValueError("nodes must contain only FlowNode instances")
            if node.id in seen_node_ids:
                raise ValueError(f"Duplicate node ID found: {node.id}")
            seen_node_ids.add(node.id)
            node_list.append(node)

        # Validate edges uniqueness and dangling refs, and prepare sorting
        seen_edge_ids: set[str] = set()
        edge_list: list[FlowEdge] = []
        for edge in self.edges:
            if not isinstance(edge, FlowEdge):
                raise ValueError("edges must contain only FlowEdge instances")
            if edge.id in seen_edge_ids:
                raise ValueError(f"Duplicate edge ID found: {edge.id}")
            if edge.source_id not in seen_node_ids:
                raise ValueError(
                    f"Dangling edge: source_id '{edge.source_id}' not found in nodes."
                )
            if edge.target_id not in seen_node_ids:
                raise ValueError(
                    f"Dangling edge: target_id '{edge.target_id}' not found in nodes."
                )
            seen_edge_ids.add(edge.id)
            edge_list.append(edge)

        # Ensure deterministic ordering by ID
        node_list.sort(key=lambda n: n.id)
        edge_list.sort(key=lambda e: e.id)

        # Bypass frozen dataclass to set attributes safely
        object.__setattr__(self, "nodes", tuple(node_list))
        object.__setattr__(self, "edges", tuple(edge_list))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        """Serializes the flow to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metadata": _to_json_compatible(self.metadata),
        }
