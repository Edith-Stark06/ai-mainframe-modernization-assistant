"""
Health API Schemas.

Purpose:
    Define the Pydantic v2 response model for the health-check endpoint.

Responsibilities:
    - Validate and serialise health-check response data.
    - Document every field with a description for automatic OpenAPI
      schema generation.

Dependencies:
    - pydantic — :class:`pydantic.BaseModel`, :func:`pydantic.Field`

Examples:
    Instantiate directly in a route handler::

        from datetime import UTC, datetime
        from app.api.schemas.health import HealthResponse

        response = HealthResponse(
            status="healthy",
            application="AI Mainframe Modernization Assistant",
            version="0.1.0",
            timestamp=datetime.now(UTC),
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["HealthResponse"]


class HealthResponse(BaseModel):
    """
    Response model for ``GET /api/v1/health``.

    Attributes:
        status:      Operational status of the service
                     (e.g. ``"healthy"``).
        application: Human-readable name of the application.
        version:     Current application version string
                     following semantic versioning (SemVer).
        timestamp:   UTC timestamp of the health-check response.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    status: str = Field(
        ...,
        description="Operational status of the service.",
        examples=["healthy"],
    )
    application: str = Field(
        ...,
        description="Human-readable name of the application.",
        examples=["AI Mainframe Modernization Assistant"],
    )
    version: str = Field(
        ...,
        description="Current application version (SemVer).",
        examples=["0.1.0"],
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp of when the response was generated.",
    )
