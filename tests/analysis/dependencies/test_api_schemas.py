"""
API Schema Validation Tests.

Tests the Pydantic schemas for Dependency Graph serialization
and validation, explicitly for Task-059 hardening.
"""

from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from app.api.schemas.dependencies import (
    DependencyGraphResponse,
    DependencyGraphNodeResponse,
    DependencyGraphEdgeResponse,
    PositionResponse,
)


def test_valid_graph() -> None:
    """A valid graph with nodes and corresponding edges must validate successfully."""
    graph = DependencyGraphResponse(
        nodes=[
            DependencyGraphNodeResponse(identifier="MAIN"),
            DependencyGraphNodeResponse(identifier="SUB"),
        ],
        edges=[
            DependencyGraphEdgeResponse(
                source="MAIN",
                target="SUB",
                dependency_type="CALL",
            )
        ],
    )
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


def test_empty_graph() -> None:
    """An empty dependency graph must validate and serialize properly."""
    graph = DependencyGraphResponse(nodes=[], edges=[])
    assert graph.nodes == []
    assert graph.edges == []

    serialized = graph.model_dump(mode="json")
    assert serialized == {"nodes": [], "edges": []}


def test_call_edge() -> None:
    """CALL dependency types must validate."""
    edge = DependencyGraphEdgeResponse(source="A", target="B", dependency_type="CALL")
    assert edge.dependency_type == "CALL"


def test_perform_edge() -> None:
    """PERFORM dependency types must validate."""
    edge = DependencyGraphEdgeResponse(
        source="A", target="B", dependency_type="PERFORM"
    )
    assert edge.dependency_type == "PERFORM"


def test_invalid_dependency_type() -> None:
    """Enum serialization requires only CALL or PERFORM. Others are rejected."""
    with pytest.raises(ValidationError):
        DependencyGraphEdgeResponse(source="A", target="B", dependency_type="INVALID")


def test_source_location() -> None:
    """Source location preservation must validate correctly."""
    edge = DependencyGraphEdgeResponse(
        source="A",
        target="B",
        dependency_type="CALL",
        source_location=PositionResponse(
            type="Position",
            line=10,
            column=5,
            offset=100,
            filename="A.cbl",
        ),
    )
    assert edge.source_location is not None
    assert edge.source_location.line == 10
    assert edge.source_location.filename == "A.cbl"


def test_edge_references_existing_nodes() -> None:
    """Edges that reference nodes present in the graph must validate."""
    graph = DependencyGraphResponse(
        nodes=[
            DependencyGraphNodeResponse(identifier="N1"),
            DependencyGraphNodeResponse(identifier="N2"),
        ],
        edges=[
            DependencyGraphEdgeResponse(
                source="N1", target="N2", dependency_type="CALL"
            )
        ],
    )
    assert graph.edges[0].source == "N1"
    assert graph.edges[0].target == "N2"


def test_invalid_dangling_edge_rejection() -> None:
    """An edge that references a missing node must be rejected."""
    with pytest.raises(ValidationError, match="does not reference an existing node"):
        DependencyGraphResponse(
            nodes=[
                DependencyGraphNodeResponse(identifier="MAIN"),
            ],
            edges=[
                DependencyGraphEdgeResponse(
                    source="MAIN", target="MISSING", dependency_type="CALL"
                )
            ],
        )

    with pytest.raises(ValidationError, match="does not reference an existing node"):
        DependencyGraphResponse(
            nodes=[
                DependencyGraphNodeResponse(identifier="MAIN"),
            ],
            edges=[
                DependencyGraphEdgeResponse(
                    source="MISSING", target="MAIN", dependency_type="CALL"
                )
            ],
        )


def test_empty_node_identifier_rejection() -> None:
    """Node identifiers must be non-empty strings."""
    with pytest.raises(ValidationError):
        DependencyGraphNodeResponse(identifier="")


def test_deterministic_serialization() -> None:
    """Graph models serialize deterministically into dicts and JSON."""
    graph = DependencyGraphResponse(
        nodes=[
            DependencyGraphNodeResponse(identifier="MAIN"),
            DependencyGraphNodeResponse(identifier="SUB"),
        ],
        edges=[
            DependencyGraphEdgeResponse(
                source="MAIN",
                target="SUB",
                dependency_type="PERFORM",
            )
        ],
    )
    data = graph.model_dump(mode="json")

    assert "nodes" in data
    assert "edges" in data

    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["identifier"] == "MAIN"
    assert data["nodes"][1]["identifier"] == "SUB"

    assert len(data["edges"]) == 1
    assert data["edges"][0]["source"] == "MAIN"
    assert data["edges"][0]["target"] == "SUB"
    assert data["edges"][0]["dependency_type"] == "PERFORM"

    json_str = json.dumps(data, sort_keys=True)
    assert '"MAIN"' in json_str
    assert '"SUB"' in json_str
    assert '"PERFORM"' in json_str


def test_backward_compatibility_fields() -> None:
    """DependencyGraphResponse must expose nodes and edges to ensure compatibility."""
    schema = DependencyGraphResponse.model_json_schema()
    properties = schema.get("properties", {})
    assert "nodes" in properties
    assert "edges" in properties
