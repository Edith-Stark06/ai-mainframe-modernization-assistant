"""
Workspace File Source Context API Schemas.

Purpose:
    Define Pydantic v2 response models for the workspace file source
    context endpoint.

Responsibilities:
    - Expose ``FileResponse`` — typed response schema for
      ``GET /api/v1/workspaces/{workspace_id}/files/{filename}``.
    - Carry source content and readily available metadata.

Non-responsibilities:
    - Compiler logic or pipeline orchestration.
    - File ingestion or validation.
    - Persistence or API exposure beyond the response envelope.

Dependencies:
    - pydantic — Pydantic v2 BaseModel, Field, ConfigDict

Examples:
    Building a response::

        from app.api.schemas.files import FileResponse

        response = FileResponse(
            success=True,
            workspace_id="ws-uuid",
            filename="payroll.cbl",
            content="IDENTIFICATION DIVISION.\\n...",
            extension=".cbl",
            size_bytes=1024,
            sha256="abc123...",
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["FileResponse"]


class FileResponse(BaseModel):
    """
    Response envelope for the workspace file source context endpoint.

    Attributes:
        success:
            ``True`` if the file was read successfully.
        workspace_id:
            UUID4 string of the workspace containing the file.
        filename:
            Basename of the requested file.
        content:
            UTF-8 source content of the file.
        extension:
            Lowercase dot-prefixed file extension.
        size_bytes:
            File size in bytes.
        sha256:
            Hex-encoded SHA-256 digest of the file content.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    success: bool = Field(
        default=True,
        description="Always True for successful file retrieval.",
    )
    workspace_id: str = Field(
        ...,
        description="UUID4 of the workspace containing the file.",
    )
    filename: str = Field(
        ...,
        description="Basename of the requested file.",
    )
    content: str = Field(
        ...,
        description="UTF-8 source content of the file.",
    )
    extension: str = Field(
        ...,
        description="Lowercase dot-prefixed file extension.",
        examples=[".cbl"],
    )
    size_bytes: int = Field(
        ...,
        ge=0,
        description="File size in bytes.",
    )
    sha256: str = Field(
        ...,
        description="Hex-encoded SHA-256 digest of the file content.",
    )
