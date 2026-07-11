"""
Workspace Intelligence API Schemas.

Purpose:
    Define Pydantic v2 response models for the workspace intelligence
    endpoints: inventory and summary.

Responsibilities:
    - Expose ``ScannedFileSchema`` — API-layer representation of a
      discovered file, mirroring :class:`app.workspace.models.ScannedFile`.
    - Expose ``InventoryResponse`` — response envelope for
      ``GET /workspaces/{workspace_id}/inventory``.
    - Expose ``TypeCountSchema`` — serialisable per-type count record.
    - Expose ``SummaryResponse`` — response envelope for
      ``GET /workspaces/{workspace_id}/summary``.
    - Keep these models decoupled from domain models per architecture rules.

Dependencies:
    - pydantic — Pydantic v2 BaseModel, Field, ConfigDict

Examples:
    Building a response from a :class:`~app.workspace.models.WorkspaceInventory`::

        from app.api.schemas.workspace import InventoryResponse, ScannedFileSchema

        response = InventoryResponse(
            workspace_id=inv.workspace_id,
            files=[ScannedFileSchema(**f.model_dump()) for f in inv.files],
            total_files=inv.total_files,
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "InventoryResponse",
    "ScannedFileSchema",
    "SummaryResponse",
    "TypeCountSchema",
]


class ScannedFileSchema(BaseModel):
    """
    API-layer representation of a single scanned file.

    Mirrors :class:`app.workspace.models.ScannedFile` but is defined in
    the API layer to preserve domain-model independence.

    Attributes:
        path:       Absolute filesystem path (or ZIP virtual path).
        filename:   Basename of the file.
        extension:  Lowercase dot-prefixed extension.
        sha256:     Hex-encoded SHA-256 digest.
        size_bytes: File size in bytes.
        file_type:  Classified file type string.
        scanned_at: UTC timestamp of when the record was created.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    path: str = Field(..., description="Absolute filesystem path to the file.")
    filename: str = Field(
        ..., description="Basename of the file.", examples=["payroll.cbl"]
    )
    extension: str = Field(
        ..., description="Lowercase dot-prefixed extension.", examples=[".cbl"]
    )
    sha256: str = Field(..., description="Hex-encoded SHA-256 digest.")
    size_bytes: int = Field(..., ge=0, description="File size in bytes.")
    file_type: str = Field(
        ..., description="Classified file type.", examples=["COBOL", "JCL"]
    )
    scanned_at: datetime = Field(
        ..., description="UTC timestamp of scan record creation."
    )


class InventoryResponse(BaseModel):
    """
    Response envelope for ``GET /workspaces/{workspace_id}/inventory``.

    Attributes:
        success:      Always ``True`` on success.
        workspace_id: UUID4 of the scanned workspace.
        files:        Ordered list of scanned file records.
        total_files:  Total number of discovered files.
        scanned_at:   UTC timestamp of when the scan completed.
    """

    model_config = ConfigDict(populate_by_name=True)

    success: bool = Field(
        default=True, description="Always True for successful responses."
    )
    workspace_id: str = Field(..., description="UUID4 of the scanned workspace.")
    files: list[ScannedFileSchema] = Field(..., description="Scanned file records.")
    total_files: int = Field(..., ge=0, description="Total discovered files.")
    scanned_at: datetime = Field(..., description="UTC timestamp of scan completion.")


class TypeCountSchema(BaseModel):
    """
    Serialisable per-type file count record for the summary response.

    Attributes:
        file_type: The classified file type label.
        count:     Number of files of this type.
    """

    model_config = ConfigDict(populate_by_name=True)

    file_type: str = Field(
        ..., description="File type label.", examples=["COBOL", "JCL"]
    )
    count: int = Field(..., ge=0, description="Number of files of this type.")


class SummaryResponse(BaseModel):
    """
    Response envelope for ``GET /workspaces/{workspace_id}/summary``.

    Attributes:
        success:           Always ``True`` on success.
        workspace_id:      UUID4 of the summarised workspace.
        total_files:       Total number of files discovered.
        by_type:           Per-type counts, sorted by count descending.
        total_size_bytes:  Cumulative size of all files in bytes.
        scanned_at:        UTC timestamp of when the summary was generated.
    """

    model_config = ConfigDict(populate_by_name=True)

    success: bool = Field(
        default=True, description="Always True for successful responses."
    )
    workspace_id: str = Field(..., description="UUID4 of the summarised workspace.")
    total_files: int = Field(..., ge=0, description="Total files discovered.")
    by_type: list[TypeCountSchema] = Field(
        ..., description="Per-type counts, descending."
    )
    total_size_bytes: int = Field(
        ..., ge=0, description="Cumulative file size in bytes."
    )
    scanned_at: datetime = Field(
        ..., description="UTC timestamp of summary generation."
    )
