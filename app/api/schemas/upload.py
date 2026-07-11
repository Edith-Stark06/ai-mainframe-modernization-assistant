"""
Upload API Response Schemas.

Purpose:
    Define Pydantic v2 request and response models for the
    ``POST /api/v1/upload`` endpoint.

Responsibilities:
    - Expose ``FileMetadataSchema`` — a serialisable representation of
      :class:`app.ingestion.models.FileMetadata` for API clients.
    - Expose ``UploadResponse`` — the complete upload endpoint response
      envelope containing the workspace ID, per-file metadata, and summary
      statistics.

Dependencies:
    - pydantic — Pydantic v2 BaseModel, Field, ConfigDict

Examples:
    Building a response from an :class:`~app.ingestion.models.IngestionResult`::

        from app.api.schemas.upload import UploadResponse, FileMetadataSchema

        response = UploadResponse(
            workspace_id=result.workspace.workspace_id,
            files=[
                FileMetadataSchema(**m.model_dump()) for m in result.files
            ],
            total_files=result.total_files,
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["FileMetadataSchema", "UploadResponse"]


class FileMetadataSchema(BaseModel):
    """
    Serialisable representation of a single ingested file's metadata.

    Mirrors :class:`app.ingestion.models.FileMetadata` but is defined
    in the API layer to keep the domain models independent of FastAPI.

    Attributes:
        filename:     Original filename supplied by the client.
        extension:    Lowercase file extension including the leading dot.
        size_bytes:   File size in bytes.
        sha256:       Hex-encoded SHA-256 digest of the file content.
        encoding:     Detected character encoding of the file content.
        workspace_id: UUID4 string of the parent workspace.
        created_at:   UTC timestamp of when the metadata was extracted.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    filename: str = Field(
        ...,
        description="Original filename supplied by the client.",
        examples=["payroll.cbl"],
    )
    extension: str = Field(
        ...,
        description="Lowercase file extension (e.g. '.cbl').",
        examples=[".cbl"],
    )
    size_bytes: int = Field(
        ...,
        ge=0,
        description="File size in bytes.",
        examples=[4096],
    )
    sha256: str = Field(
        ...,
        description="Hex-encoded SHA-256 digest of the file content.",
    )
    encoding: str = Field(
        ...,
        description="Detected character encoding.",
        examples=["UTF-8", "ASCII", "EBCDIC"],
    )
    workspace_id: str = Field(
        ...,
        description="UUID4 string of the parent workspace.",
    )
    created_at: datetime = Field(
        ...,
        description="UTC timestamp of when this metadata record was created.",
    )


class UploadResponse(BaseModel):
    """
    Response envelope for ``POST /api/v1/upload``.

    Attributes:
        success:      Always ``True`` on a successful upload.
        workspace_id: UUID4 string identifying the upload workspace.
        files:        List of :class:`FileMetadataSchema` for each
                      ingested file.
        total_files:  Number of files successfully ingested.
        message:      Human-readable summary of the operation.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    success: bool = Field(
        default=True,
        description="Always True for successful upload responses.",
    )
    workspace_id: str = Field(
        ...,
        description="UUID4 of the workspace created for this upload.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    files: list[FileMetadataSchema] = Field(
        ...,
        description="Metadata for each successfully ingested file.",
    )
    total_files: int = Field(
        ...,
        ge=0,
        description="Total number of files successfully ingested.",
        examples=[3],
    )
    message: str = Field(
        ...,
        description="Human-readable summary message.",
        examples=["3 file(s) ingested successfully."],
    )
