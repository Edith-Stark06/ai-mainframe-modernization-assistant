"""
Base API Response Schemas.

Purpose:
    Provide a canonical Pydantic v2 base model that all API response
    schemas should inherit from, ensuring a consistent response envelope
    across the entire API surface.

Responsibilities:
    - Define shared response fields (``success``, ``message``,
      ``timestamp``).
    - Enforce Pydantic v2 configuration (``model_config``) globally.
    - Expose ``__all__`` for clean star-imports where appropriate.

Dependencies:
    - pydantic — :class:`pydantic.BaseModel`, :func:`pydantic.Field`

Examples:
    Extend ``APIResponse`` for a domain-specific response::

        from app.api.schemas.base import APIResponse

        class FileUploadResponse(APIResponse):
            file_id: str
            filename: str
            size_bytes: int

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["APIResponse"]


class APIResponse(BaseModel):
    """
    Base response envelope for all API responses.

    All domain-specific response models should inherit from this class to
    guarantee a consistent structure across the API surface.

    Attributes:
        success:   Indicates whether the operation succeeded.
        message:   Human-readable status message.
        timestamp: UTC timestamp of when the response was generated.
                   Defaults to the current UTC time at instantiation.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    success: bool = True
    message: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the response.",
    )
