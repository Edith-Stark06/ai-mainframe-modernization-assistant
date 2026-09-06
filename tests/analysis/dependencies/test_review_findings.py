"""
Focused regression tests for the post-#111 code review findings.

Covers:
    - Finding 2: the flat dependency API response must be able to
      expose VARIABLE_READ/VARIABLE_WRITE/CONDITION, while the
      workspace-resolution graph edge schema must reject them (it is
      restricted to structural CALL/PERFORM/COPY dependencies).
    - Finding 3: Dependency.confidence must reject values outside the
      documented [0.0, 1.0] range rather than silently accepting them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.analysis.dependencies.models import (
    STRUCTURAL_DEPENDENCY_TYPES,
    Dependency,
    DependencyType,
)
from app.api.schemas.dependencies import (
    DependencyGraphEdgeResponse,
    DependencyResponse,
)

# ----------------------------------------------------------------------
# Finding 2: flat response vs. structural graph edge schema
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "dependency_type",
    ["CALL", "PERFORM", "COPY", "VARIABLE_READ", "VARIABLE_WRITE", "CONDITION"],
)
def test_flat_dependency_response_accepts_every_dependency_type(
    dependency_type: str,
) -> None:
    """The flat dependency list must expose every DependencyType, structural or not."""
    dep = DependencyResponse(type=dependency_type, target="X")
    assert dep.type == dependency_type


@pytest.mark.parametrize("dependency_type", ["CALL", "PERFORM", "COPY"])
def test_graph_edge_schema_accepts_structural_types(dependency_type: str) -> None:
    """The workspace-resolution graph edge schema accepts CALL/PERFORM/COPY."""
    edge = DependencyGraphEdgeResponse(
        source="A", target="B", dependency_type=dependency_type
    )
    assert edge.dependency_type == dependency_type


@pytest.mark.parametrize(
    "dependency_type", ["VARIABLE_READ", "VARIABLE_WRITE", "CONDITION"]
)
def test_graph_edge_schema_rejects_non_structural_types(dependency_type: str) -> None:
    """
    The workspace-resolution graph edge schema must reject
    VARIABLE_READ/VARIABLE_WRITE/CONDITION -- a variable or condition
    reference is never a workspace file to resolve, so it must never be
    representable as a graph edge, not merely omitted by convention.
    """
    with pytest.raises(ValidationError):
        DependencyGraphEdgeResponse(
            source="A", target="B", dependency_type=dependency_type
        )


def test_structural_dependency_types_constant_is_exactly_call_perform_copy() -> None:
    assert STRUCTURAL_DEPENDENCY_TYPES == frozenset(
        {DependencyType.CALL, DependencyType.PERFORM, DependencyType.COPY}
    )


def test_variable_and_condition_types_are_not_structural() -> None:
    assert DependencyType.VARIABLE_READ not in STRUCTURAL_DEPENDENCY_TYPES
    assert DependencyType.VARIABLE_WRITE not in STRUCTURAL_DEPENDENCY_TYPES
    assert DependencyType.CONDITION not in STRUCTURAL_DEPENDENCY_TYPES


def test_workspace_graph_construction_excludes_variable_and_condition_dependencies() -> (
    None
):
    """
    End-to-end (below the API layer): filtering a mixed dependency list
    down to STRUCTURAL_DEPENDENCY_TYPES -- exactly what
    app.api.routers.analysis does before building the workspace
    resolution graph -- must drop every VARIABLE_READ/VARIABLE_WRITE/
    CONDITION dependency and keep every CALL/PERFORM/COPY one.
    """
    deps = [
        Dependency(type=DependencyType.CALL, target="SUBPROG", source="MAIN"),
        Dependency(type=DependencyType.PERFORM, target="WORKER", source="MAIN"),
        Dependency(type=DependencyType.COPY, target="COPYBOOK", source="MAIN"),
        Dependency(type=DependencyType.VARIABLE_READ, target="WS-A", source="MAIN"),
        Dependency(type=DependencyType.VARIABLE_WRITE, target="WS-B", source="MAIN"),
        Dependency(type=DependencyType.CONDITION, target="WS-FLAG", source="MAIN"),
    ]

    structural = [d for d in deps if d.type in STRUCTURAL_DEPENDENCY_TYPES]

    assert {d.target for d in structural} == {"SUBPROG", "WORKER", "COPYBOOK"}
    assert {d.type for d in structural} == {
        DependencyType.CALL,
        DependencyType.PERFORM,
        DependencyType.COPY,
    }


# ----------------------------------------------------------------------
# Finding 3: Dependency.confidence validation
# ----------------------------------------------------------------------


def test_confidence_zero_is_accepted() -> None:
    dep = Dependency(type=DependencyType.CALL, target="X", confidence=0.0)
    assert dep.confidence == 0.0


def test_confidence_one_is_accepted() -> None:
    dep = Dependency(type=DependencyType.CALL, target="X", confidence=1.0)
    assert dep.confidence == 1.0


def test_confidence_default_matches_normal_analyzer_value() -> None:
    """The analyzer never sets confidence explicitly; the default must stay 1.0."""
    dep = Dependency(type=DependencyType.PERFORM, target="X")
    assert dep.confidence == 1.0


def test_confidence_below_zero_is_rejected() -> None:
    with pytest.raises(ValueError):
        Dependency(type=DependencyType.CALL, target="X", confidence=-0.01)


def test_confidence_above_one_is_rejected() -> None:
    with pytest.raises(ValueError):
        Dependency(type=DependencyType.CALL, target="X", confidence=1.01)
