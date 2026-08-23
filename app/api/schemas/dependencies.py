"""
Dependency API Schemas.

Purpose:
    Define typed Pydantic v2 response models for dependency data
    exposed by the analysis API endpoint.

Responsibilities:
    - Expose ``PositionResponse`` — typed representation of a serialized
      source position.
    - Expose ``DependencyResponse`` — typed representation of a serialized
      COBOL dependency.

Non-responsibilities:
    - Dependency extraction logic (belongs to DependencyAnalyzer).
    - Dependency serialization logic (belongs to serializers).
    - Parser or lexer changes.

Dependencies:
    - pydantic — Pydantic v2 BaseModel, Field, ConfigDict

Examples:
    Validating a dependency response::

        from app.api.schemas.dependencies import DependencyResponse

        dep = DependencyResponse(
            type="CALL",
            target='"CUSTOMER-SERVICE"',
            source_location={"type": "Position", "line": 6, "column": 13, "offset": 42, "filename": "test.cbl"},
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DependencyAnalysisSummaryResponse",
    "DependencyResponse",
    "PositionResponse",
]


class PositionResponse(BaseModel):
    """
    Typed representation of a serialized source position.

    Attributes:
        type:
            Discriminator emitted by the serializer identifying this as
            a ``Position`` structure.
        line:
            One-based line number within the source file.
        column:
            One-based column number within the current line.
        offset:
            Zero-based byte offset from the beginning of the source string.
        filename:
            Path of the source file that contains this position.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    type: str = Field(
        ...,
        description="Discriminator identifying the position structure.",
    )
    line: int = Field(
        ...,
        description="One-based line number within the source file.",
    )
    column: int = Field(
        ...,
        description="One-based column number within the current line.",
    )
    offset: int = Field(
        ...,
        description="Zero-based byte offset from the beginning of the source string.",
    )
    filename: str = Field(
        ...,
        description="Path of the source file that contains this position.",
    )


class DependencyResponse(BaseModel):
    """
    Typed representation of a serialized COBOL dependency.

    Attributes:
        type:
            Dependency kind as a string value (``CALL`` or ``PERFORM``).
        target:
            Literal target name as extracted by the parser.
        source_location:
            Source location of the dependency, or ``None`` if unavailable.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    type: str = Field(
        ...,
        description="Dependency kind (CALL or PERFORM).",
    )
    target: str = Field(
        ...,
        description="Literal target name as extracted by the parser.",
    )
    source_location: PositionResponse | None = Field(
        default=None,
        description="Source location of the dependency, or null if unavailable.",
    )


class DependencyAnalysisSummaryResponse(BaseModel):
    """
    Typed representation of a serialized dependency analysis summary.

    Attributes:
        node_count:
            Total number of nodes in the dependency graph.
        edge_count:
            Total number of edges in the dependency graph.
        resolved_target_count:
            Number of resolution targets that were successfully resolved.
        unresolved_target_count:
            Number of resolution targets that could not be resolved.
        ambiguous_target_count:
            Number of resolution targets that had ambiguous resolutions.
        dependency_counts:
            Counts of dependencies grouped by their type (e.g. CALL, PERFORM).
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    node_count: int = Field(
        ...,
        description="Total number of nodes in the dependency graph.",
    )
    edge_count: int = Field(
        ...,
        description="Total number of edges in the dependency graph.",
    )
    resolved_target_count: int = Field(
        ...,
        description="Number of resolution targets that were successfully resolved.",
    )
    unresolved_target_count: int = Field(
        ...,
        description="Number of resolution targets that could not be resolved.",
    )
    ambiguous_target_count: int = Field(
        ...,
        description="Number of resolution targets that had ambiguous resolutions.",
    )
    dependency_counts: dict[str, int] = Field(
        ...,
        description="Counts of dependencies grouped by their type (e.g. CALL, PERFORM).",
    )
