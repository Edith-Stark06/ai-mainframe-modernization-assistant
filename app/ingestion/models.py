"""
Ingestion Domain Models.

Purpose:
    Define the core Pydantic v2 domain models used throughout the file
    ingestion pipeline.  These models are the canonical data structures
    that flow between the uploader, validator, metadata extractor, and
    the API layer.

Responsibilities:
    - Model a ``WorkspaceRecord`` that tracks workspace identity and
      lifecycle timestamps.
    - Model ``FileMetadata`` capturing every attribute extracted from a
      successfully ingested file.
    - Model an ``IngestionResult`` that bundles the workspace record and
      the list of ingested files for serialisation.
    - Remain entirely independent of FastAPI (domain layer rule).

Dependencies:
    - pydantic  — Pydantic v2 BaseModel, Field, ConfigDict
    - Python standard library (``datetime``, ``uuid``)

Examples:
    Creating a workspace record::

        from app.ingestion.models import WorkspaceRecord

        record = WorkspaceRecord(workspace_id=str(uuid.uuid4()))

    Accessing extracted metadata::

        from app.ingestion.models import FileMetadata

        meta = FileMetadata(
            filename="payroll.cbl",
            extension=".cbl",
            size_bytes=4096,
            sha256="abc123...",
            encoding="UTF-8",
            workspace_id="ws-uuid",
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FileMetadata",
    "IngestionResult",
    "WorkspaceRecord",
]

# ---------------------------------------------------------------------------
# Supported file extensions
# ---------------------------------------------------------------------------

SupportedExtension = Literal[".cbl", ".cob", ".cpy", ".jcl", ".txt", ".zip"]

# ---------------------------------------------------------------------------
# Encoding literals
# ---------------------------------------------------------------------------

DetectedEncoding = Literal["UTF-8", "ASCII", "UTF-16", "EBCDIC", "UNKNOWN"]


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class WorkspaceRecord(BaseModel):
    """
    Represents a logical workspace that groups ingested mainframe files.

    A workspace is created for each upload session and provides the
    on-disk isolation boundary for the files being processed.

    Attributes:
        workspace_id: UUID4 string uniquely identifying the workspace.
        path:         Absolute path to the workspace directory on disk.
        created_at:   UTC timestamp of when the workspace was created.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    workspace_id: str = Field(
        ...,
        description="UUID4 string that uniquely identifies this workspace.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    path: str = Field(
        ...,
        description="Absolute filesystem path to the workspace directory.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of workspace creation.",
    )


class FileMetadata(BaseModel):
    """
    Metadata extracted from a single successfully ingested file.

    Every file that passes validation is represented by a
    ``FileMetadata`` instance that is stored alongside the raw file in
    the workspace directory.

    Attributes:
        filename:     Original filename as supplied by the client.
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
        examples=[".cbl", ".jcl"],
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
        examples=["a3f1..."],
    )
    encoding: str = Field(
        ...,
        description="Detected character encoding of the file content.",
        examples=["UTF-8", "EBCDIC"],
    )
    workspace_id: str = Field(
        ...,
        description="UUID4 string of the parent workspace.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of when this metadata record was created.",
    )


class IngestionResult(BaseModel):
    """
    Aggregate result returned after a complete upload/ingestion session.

    Bundles the workspace record with the list of successfully ingested
    file metadata records so that the API layer can serialise a single
    coherent response.

    Attributes:
        workspace:    The :class:`WorkspaceRecord` created for this session.
        files:        Ordered list of :class:`FileMetadata` for each ingested
                      file.
        total_files:  Total number of files successfully ingested.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    workspace: WorkspaceRecord = Field(
        ...,
        description="Workspace record for this upload session.",
    )
    files: list[FileMetadata] = Field(
        default_factory=list,
        description="Metadata records for each successfully ingested file.",
    )
    total_files: int = Field(
        ...,
        ge=0,
        description="Total number of files successfully ingested.",
    )
