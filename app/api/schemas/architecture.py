"""
Architecture API Schemas.

The response wraps the existing, already-typed
:class:`~app.java_modernization.architecture.models.JavaArchitecture`
(#125) directly -- it is not redefined here. This is the adapter
principle: the API layer types its envelope (workspace/filename/
availability/reason) around the real domain model, rather than
re-describing its fields a second time.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.java_modernization.architecture.models import JavaArchitecture

__all__ = ["ArchitectureResponse"]


class ArchitectureResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str
    filename: str
    available: bool = Field(
        ...,
        description=(
            "False when architecture generation could not run at all "
            "(e.g. the source has no usable AST) -- see 'reason'. This "
            "is a structural gate, never a fabricated architecture."
        ),
    )
    reason: str | None = Field(
        default=None,
        description="Populated only when available is False.",
    )
    architecture: JavaArchitecture | None = Field(
        default=None,
        description="The real, evidence-based #125 architecture, or null when unavailable.",
    )
