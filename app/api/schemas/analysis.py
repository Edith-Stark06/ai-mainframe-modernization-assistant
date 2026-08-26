"""
Analysis API Schemas.

Purpose:
    Define Pydantic v2 request and response models for the analysis
    API endpoint.

Responsibilities:
    - Expose ``AnalysisRequest`` — typed request schema identifying the
      source file to analyze within a workspace.
    - Expose ``AnalysisResponse`` — response envelope carrying the
      serialized analysis result.

Non-responsibilities:
    - Compiler logic or pipeline orchestration.
    - AST / IR / diagnostic serialization (delegated to TASK-043 serializers).
    - Persistence or API exposure beyond the response envelope.

Dependencies:
    - pydantic — Pydantic v2 BaseModel, Field, ConfigDict

Examples:
    Building a request::

        from app.api.schemas.analysis import AnalysisRequest

        request = AnalysisRequest(filename="payroll.cbl")

    Building a response::

        from app.api.schemas.analysis import AnalysisResponse

        response = AnalysisResponse(
            success=True,
            workspace_id="ws-uuid",
            filename="payroll.cbl",
            java_source="public class Payroll { ... }",
            ast={...},
            ir={...},
            diagnostics=[...],
            error=None,
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.dependencies import (
    DependencyAnalysisSummaryResponse,
    DependencyGraphResponse,
    DependencyResponse,
)
from app.api.schemas.rules import BusinessRuleResponse
from app.api.schemas.ai import AIAnalysisResponse, AICapabilityRequest

__all__ = [
    "AnalysisRequest",
    "AnalysisResponse",
    "AnalysisSourceMetadata",
    "AnalysisStatus",
    "BusinessRuleResponse",
    "DependencyAnalysisSummaryResponse",
    "DependencyGraphResponse",
    "DependencyResponse",
]


class AnalysisStatus(str, Enum):
    """
    Execution status of the analysis pipeline.

    Attributes:
        SUCCESS: The analysis pipeline completed and the source has no semantic errors.
        ANALYSIS_ERROR: The analysis pipeline completed but the source has semantic errors.
        INTERNAL_ERROR: The analysis pipeline encountered an unexpected internal exception.
    """

    SUCCESS = "SUCCESS"
    ANALYSIS_ERROR = "ANALYSIS_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AnalysisRequest(BaseModel):
    """
    Request schema for the analysis endpoint.

    Attributes:
        filename:
            Basename of the source file to analyze within the requested
            workspace.  The file must exist in the workspace root and
            have a supported analysis extension (``.cbl`` or ``.cob``).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    filename: str = Field(
        ...,
        min_length=1,
        description="Basename of the COBOL source file to analyze.",
        examples=["payroll.cbl"],
    )
    ai_capabilities: list[AICapabilityRequest] | None = Field(
        default=None,
        description="Optional list of AI capabilities to invoke during analysis.",
        examples=[[AICapabilityRequest.EXPLANATION, AICapabilityRequest.DOCUMENTATION]],
    )


class AnalysisSourceMetadata(BaseModel):
    """
    Metadata identifying the exact workspace file that was analyzed.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    extension: str = Field(
        ...,
        description="Lowercase file extension.",
    )
    size_bytes: int = Field(
        ...,
        description="File size in bytes.",
    )
    sha256: str = Field(
        ...,
        description="Hex-encoded SHA-256 digest of the file content.",
    )


class AnalysisResponse(BaseModel):
    """
    Response envelope for the analysis endpoint.

    Attributes:
        success:
            ``True`` if the analysis pipeline completed without semantic
            errors or unexpected exceptions.
        analysis_id:
            Server-generated unique identifier for this analysis request.
        workspace_id:
            UUID4 string of the workspace containing the analyzed file.
        filename:
            Basename of the analyzed source file.
        source_metadata:
            Metadata about the exact source file analyzed.
        java_source:
            Generated Java source string, or empty string if analysis
            failed before code generation.
        ast:
            JSON-safe serialized AST, or ``None`` if parsing did not
            complete.
        ir:
            JSON-safe serialized IR, or ``None`` if IR construction did
            not complete.
        diagnostics:
            Serialized semantic and backend diagnostics.
        dependencies:
            Serialized COBOL dependencies extracted from the source.
        dependency_summary:
            Summary statistics of the dependency graph and resolutions, or
            ``None`` if unavailable.
        dependency_graph:
            Serialized dependency graph containing nodes and edges, or
            ``None`` if unavailable.
        error:
            Human-readable error message, or ``None`` if the analysis
            succeeded.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    success: bool = Field(
        ...,
        description="Whether the analysis completed successfully.",
    )
    status: AnalysisStatus = Field(
        ...,
        description="Execution status of the analysis pipeline.",
    )
    analysis_id: str = Field(
        ...,
        description="Server-generated unique identifier for this analysis request.",
    )
    workspace_id: str = Field(
        ...,
        description="UUID4 of the workspace containing the analyzed file.",
    )
    filename: str = Field(
        ...,
        description="Basename of the analyzed source file.",
    )
    source_metadata: AnalysisSourceMetadata = Field(
        ...,
        description="Metadata describing the exact source file analyzed.",
    )
    java_source: str = Field(
        ...,
        description="Generated Java source string.",
    )
    ast: dict[str, Any] | None = Field(
        default=None,
        description="JSON-safe serialized AST, or null if unavailable.",
    )
    ir: dict[str, Any] | None = Field(
        default=None,
        description="JSON-safe serialized IR, or null if unavailable.",
    )
    diagnostics: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Serialized semantic and backend diagnostics.",
    )
    dependencies: list[DependencyResponse] = Field(
        default_factory=list,
        description="Serialized COBOL dependencies.",
    )
    dependency_summary: DependencyAnalysisSummaryResponse | None = Field(
        default=None,
        description="Summary statistics of the dependency graph and resolutions, or null if unavailable.",
    )
    dependency_graph: DependencyGraphResponse | None = Field(
        default=None,
        description="Serialized dependency graph containing nodes and edges, or null if unavailable.",
    )
    business_rules: list[BusinessRuleResponse] | None = Field(
        default=None,
        description="Normalized business rules extracted from the source, or null if analysis failed before AST construction.",
    )
    error: str | None = Field(
        default=None,
        description="Human-readable error message, or null on success.",
    )
    ai_analysis: AIAnalysisResponse | None = Field(
        default=None,
        description="Optional AI analysis result, if requested and successfully produced.",
    )
