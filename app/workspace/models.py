"""
Workspace Intelligence Domain Models.

Purpose:
    Define the Pydantic v2 domain models used by the workspace intelligence
    subsystem — scanner, classifier, inventory, and summary.  These models
    are the canonical data structures passed between the layers and
    serialised by the API.

Responsibilities:
    - Define ``FileType`` — an enumeration of recognised mainframe file
      types (COBOL, Copybook, JCL, PROC, BMS, XML, JSON, Text, Unknown).
    - Define ``ScannedFile`` — a record for a single discovered file with
      path, filename, extension, SHA-256 hash, size, and classified type.
    - Define ``WorkspaceInventory`` — the ordered collection of all
      ``ScannedFile`` records for a workspace.
    - Define ``TypeCount`` — a count of files for a single type, used in
      summary statistics.
    - Define ``WorkspaceSummary`` — aggregate statistics over a workspace.
    - Remain entirely independent of FastAPI (domain layer rule).

Dependencies:
    - pydantic  — Pydantic v2 BaseModel, Field, ConfigDict
    - enum      — :class:`str` + :class:`enum.Enum` for ``FileType``

Examples:
    Building a scanned file record::

        from app.workspace.models import ScannedFile, FileType

        record = ScannedFile(
            path="/workspace/ws-001/payroll.cbl",
            filename="payroll.cbl",
            extension=".cbl",
            sha256="a3f1...",
            size_bytes=4096,
            file_type=FileType.COBOL,
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FileType",
    "ScannedFile",
    "TypeCount",
    "WorkspaceInventory",
    "WorkspaceSummary",
]


# ---------------------------------------------------------------------------
# File type enumeration
# ---------------------------------------------------------------------------


class FileType(str, Enum):
    """
    Enumeration of recognised mainframe and auxiliary file types.

    Members use lowercase string values so they serialise cleanly to JSON
    and are human-readable in log messages.

    Attributes:
        COBOL:    COBOL source programs (.cbl, .cob).
        COPYBOOK: COBOL Copybook definitions (.cpy).
        JCL:      Job Control Language batch job definitions (.jcl).
        PROC:     JCL procedures stored in a procedure library (.proc).
        BMS:      Basic Mapping Support screen definitions (.bms).
        XML:      XML documents (.xml).
        JSON:     JSON documents (.json).
        TEXT:     Plain text files (.txt).
        UNKNOWN:  Files whose type cannot be determined.
    """

    COBOL = "COBOL"
    COPYBOOK = "Copybook"
    JCL = "JCL"
    PROC = "PROC"
    BMS = "BMS"
    XML = "XML"
    JSON = "JSON"
    TEXT = "Text"
    UNKNOWN = "Unknown"


# ---------------------------------------------------------------------------
# Per-file record
# ---------------------------------------------------------------------------


class ScannedFile(BaseModel):
    """
    Metadata record for a single file discovered during a workspace scan.

    Attributes:
        path:       Absolute filesystem path to the file.
        filename:   Basename of the file (e.g. ``"payroll.cbl"``).
        extension:  Lowercase dot-prefixed extension (e.g. ``".cbl"``).
        sha256:     Hex-encoded SHA-256 digest of the file content.
        size_bytes: File size in bytes.
        file_type:  Classified :class:`FileType` of the file.
        scanned_at: UTC timestamp of when the scan record was created.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )

    path: str = Field(
        ...,
        description="Absolute filesystem path to the file.",
    )
    filename: str = Field(
        ...,
        description="Basename of the file.",
        examples=["payroll.cbl"],
    )
    extension: str = Field(
        ...,
        description="Lowercase dot-prefixed extension.",
        examples=[".cbl", ".jcl"],
    )
    sha256: str = Field(
        ...,
        description="Hex-encoded SHA-256 digest of file content.",
    )
    size_bytes: int = Field(
        ...,
        ge=0,
        description="File size in bytes.",
    )
    file_type: FileType = Field(
        ...,
        description="Classified type of the file.",
    )
    scanned_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of when this record was created.",
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class WorkspaceInventory(BaseModel):
    """
    Complete inventory of all files discovered in a workspace scan.

    Attributes:
        workspace_id: UUID4 string of the scanned workspace.
        files:        Ordered list of :class:`ScannedFile` records.
        total_files:  Total count of all discovered files.
        scanned_at:   UTC timestamp of when the scan completed.
    """

    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str = Field(
        ...,
        description="UUID4 string of the scanned workspace.",
    )
    files: list[ScannedFile] = Field(
        default_factory=list,
        description="Ordered list of scanned file records.",
    )
    total_files: int = Field(
        ...,
        ge=0,
        description="Total number of discovered files.",
    )
    scanned_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of when the inventory scan completed.",
    )


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


class TypeCount(BaseModel):
    """
    Count of files for a single :class:`FileType` within a workspace.

    Attributes:
        file_type: The file type category.
        count:     Number of files of this type found in the workspace.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
    )

    file_type: FileType = Field(
        ...,
        description="File type category.",
    )
    count: int = Field(
        ...,
        ge=0,
        description="Number of files of this type.",
    )


class WorkspaceSummary(BaseModel):
    """
    Aggregate statistics generated from a completed workspace inventory.

    Attributes:
        workspace_id:   UUID4 string of the scanned workspace.
        total_files:    Total number of files discovered.
        by_type:        Per-type file counts, sorted by count descending.
        total_size_bytes: Cumulative size of all discovered files in bytes.
        scanned_at:     UTC timestamp of when the summary was generated.
    """

    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str = Field(
        ...,
        description="UUID4 string of the scanned workspace.",
    )
    total_files: int = Field(
        ...,
        ge=0,
        description="Total number of discovered files.",
    )
    by_type: list[TypeCount] = Field(
        default_factory=list,
        description="Per-type file counts, sorted by count descending.",
    )
    total_size_bytes: int = Field(
        ...,
        ge=0,
        description="Cumulative size of all discovered files in bytes.",
    )
    scanned_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of when the summary was generated.",
    )
