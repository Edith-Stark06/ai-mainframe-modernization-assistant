"""
AI Analysis API Schemas.

Purpose:
    Define Pydantic v2 response schemas for AI orchestration artifacts,
    such as generated code explanations and COBOL documentation.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AIAnalysisResponse",
    "CodeExplanationResponse",
    "DocumentationResponse",
    "DocumentationSectionResponse",
    "AICapabilityRequest",
]


class AICapabilityRequest(str, Enum):
    """
    Requested AI capabilities.
    """

    EXPLANATION = "EXPLANATION"
    DOCUMENTATION = "DOCUMENTATION"


class CodeExplanationResponse(BaseModel):
    """
    Response schema for generated code explanations.
    """

    model_config = ConfigDict(populate_by_name=True)

    summary: str = Field(
        ...,
        description="A high-level summary of the program's purpose.",
    )
    explanation: str = Field(
        ...,
        description="A detailed explanation of the program's operations and rules.",
    )


class DocumentationSectionResponse(BaseModel):
    """
    Response schema for a single generated documentation section.
    """

    model_config = ConfigDict(populate_by_name=True)

    heading: str = Field(
        ...,
        description="The heading of the section.",
    )
    content: str = Field(
        ...,
        description="The content of the section.",
    )


class DocumentationResponse(BaseModel):
    """
    Response schema for generated COBOL documentation.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(
        ...,
        description="The title of the documentation.",
    )
    overview: str = Field(
        ...,
        description="A high-level overview of the program.",
    )
    sections: list[DocumentationSectionResponse] = Field(
        default_factory=list,
        description="A list of specific documentation sections.",
    )


class AIAnalysisResponse(BaseModel):
    """
    Response envelope for combined AI analysis artifacts.
    """

    model_config = ConfigDict(populate_by_name=True)

    explanation: CodeExplanationResponse | None = Field(
        default=None,
        description="The generated code explanation, if requested.",
    )
    documentation: DocumentationResponse | None = Field(
        default=None,
        description="The generated COBOL documentation, if requested.",
    )
