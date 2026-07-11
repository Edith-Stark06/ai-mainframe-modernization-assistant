"""
Error Response Schemas.

Purpose:
    Define Pydantic v2 models for the canonical error envelope returned
    by every exception handler in the application.

Responsibilities:
    - Model the nested ``ErrorDetail`` payload (code, message, details).
    - Model the top-level ``ErrorResponse`` envelope that all handlers
      serialise to JSON.
    - Expose ``__all__`` for clean star-imports.

Dependencies:
    - pydantic          — :class:`pydantic.BaseModel`, :func:`pydantic.Field`
    - app.api.schemas.base — shared ``model_config``

Examples:
    Building an error response inside a handler::

        from app.api.schemas.error import ErrorDetail, ErrorResponse

        return ErrorResponse(
            error=ErrorDetail(
                code="NOT_FOUND",
                message="workspace 'ws-001' was not found.",
                details=None,
            ),
            request_id=request_id,
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ErrorDetail", "ErrorResponse"]


class ErrorDetail(BaseModel):
    """
    Nested error payload embedded in every error response envelope.

    Attributes:
        code:    Machine-readable error code (e.g. ``"NOT_FOUND"``).
        message: Human-readable description of the error.
        details: Optional structured payload with additional context
                 (validation field errors, parse location, etc.).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    code: str = Field(
        ...,
        description="Machine-readable error identifier.",
        examples=["NOT_FOUND", "VALIDATION_ERROR"],
    )
    message: str = Field(
        ...,
        description="Human-readable error description.",
    )
    details: Any = Field(
        default=None,
        description="Optional structured context (field errors, parse info, etc.).",
    )


class ErrorResponse(BaseModel):
    """
    Canonical error envelope returned by every exception handler.

    Conforms to the error response schema specified in TASK-002::

        {
            "success": false,
            "error": { "code": "...", "message": "...", "details": ... },
            "request_id": "...",
            "timestamp": "..."
        }

    Attributes:
        success:    Always ``False`` for error responses.
        error:      Nested :class:`ErrorDetail` payload.
        request_id: UUID4 correlation identifier injected by the
                    :class:`app.core.middleware.RequestIDMiddleware`.
        timestamp:  UTC ISO-8601 timestamp generated at response time.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    success: bool = Field(
        default=False,
        description="Always False for error responses.",
    )
    error: ErrorDetail = Field(
        ...,
        description="Structured error payload.",
    )
    request_id: str = Field(
        ...,
        description="UUID4 correlation identifier from the request.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of when the error response was generated.",
    )
