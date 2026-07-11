"""
Enterprise Exception Hierarchy.

Purpose:
    Define a typed, structured exception hierarchy for the
    AI-Powered Mainframe Modernization Assistant.  Every domain area
    raises a dedicated exception subclass so that handlers can respond
    with precise HTTP status codes and machine-readable error codes.

Responsibilities:
    - Provide a base ``AppException`` that carries a code, message, and
      optional contextual details.
    - Expose specialised subclasses for validation, resource lookup,
      server-side, parsing, and AI failures.
    - Remain entirely independent of FastAPI (domain layer rule).

Dependencies:
    - Python standard library only (``http``, ``typing``).

Examples:
    Raising a domain exception from a service::

        from app.core.exceptions import ResourceNotFoundException

        raise ResourceNotFoundException(
            resource="workspace",
            identifier="ws-abc123",
        )

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from http import HTTPStatus
from typing import Any

__all__ = [
    "AppException",
    "ValidationException",
    "ResourceNotFoundException",
    "InternalServerException",
    "ParsingException",
    "AIException",
]


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class AppException(Exception):
    """
    Base application exception.

    All domain-specific exceptions inherit from this class.  Handlers
    inspect ``status_code``, ``error_code``, and ``details`` to produce
    a canonical :class:`app.api.schemas.error.ErrorResponse`.

    Attributes:
        status_code: HTTP status code that should be returned to the client.
        error_code:  Machine-readable short identifier (e.g. ``"NOT_FOUND"``).
        message:     Human-readable description of the error.
        details:     Optional structured payload with extra context.
    """

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR.value
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        details: Any = None,
    ) -> None:
        """
        Initialise the base application exception.

        Args:
            message: Human-readable description of what went wrong.
            details: Optional mapping or value with additional context
                     (e.g. field names, attempted values).
        """
        super().__init__(message)
        self.message: str = message
        self.details: Any = details

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"details={self.details!r})"
        )


# ---------------------------------------------------------------------------
# Specialised exceptions
# ---------------------------------------------------------------------------


class ValidationException(AppException):
    """
    Raised when request input fails domain-level validation.

    This is distinct from Pydantic's ``RequestValidationError``; it is
    raised explicitly by services when business rules are violated.

    Attributes:
        status_code: 422 Unprocessable Entity.
        error_code:  ``"VALIDATION_ERROR"``.
    """

    status_code: int = HTTPStatus.UNPROCESSABLE_ENTITY.value
    error_code: str = "VALIDATION_ERROR"

    def __init__(
        self,
        message: str = "Request validation failed.",
        details: Any = None,
    ) -> None:
        """
        Initialise a validation exception.

        Args:
            message: Human-readable description of the validation failure.
            details: Optional mapping of field names to error messages.
        """
        super().__init__(message=message, details=details)


class ResourceNotFoundException(AppException):
    """
    Raised when a requested resource cannot be located.

    Attributes:
        status_code: 404 Not Found.
        error_code:  ``"NOT_FOUND"``.
    """

    status_code: int = HTTPStatus.NOT_FOUND.value
    error_code: str = "NOT_FOUND"

    def __init__(
        self,
        resource: str,
        identifier: str | int,
        details: Any = None,
    ) -> None:
        """
        Initialise a not-found exception.

        Args:
            resource:   Logical name of the missing resource (e.g. ``"workspace"``).
            identifier: The identifier that was looked up.
            details:    Optional extra context.
        """
        message = f"{resource} '{identifier}' was not found."
        super().__init__(message=message, details=details)
        self.resource: str = resource
        self.identifier: str | int = identifier


class InternalServerException(AppException):
    """
    Raised when an unexpected server-side failure occurs.

    Attributes:
        status_code: 500 Internal Server Error.
        error_code:  ``"INTERNAL_ERROR"``.
    """

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR.value
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "An unexpected internal error occurred.",
        details: Any = None,
    ) -> None:
        """
        Initialise an internal server exception.

        Args:
            message: Human-readable description of the failure.
            details: Optional diagnostic payload (never expose internals
                     in production responses).
        """
        super().__init__(message=message, details=details)


class ParsingException(AppException):
    """
    Raised when the COBOL / JCL / Copybook parser encounters invalid input.

    Attributes:
        status_code: 422 Unprocessable Entity.
        error_code:  ``"PARSING_ERROR"``.
    """

    status_code: int = HTTPStatus.UNPROCESSABLE_ENTITY.value
    error_code: str = "PARSING_ERROR"

    def __init__(
        self,
        message: str = "Failed to parse the supplied source file.",
        details: Any = None,
    ) -> None:
        """
        Initialise a parsing exception.

        Args:
            message: Description of the parse failure (e.g. line number,
                     unexpected token).
            details: Optional structured parse-error payload.
        """
        super().__init__(message=message, details=details)


class AIException(AppException):
    """
    Raised when an AI / LLM back-end call fails.

    Attributes:
        status_code: 503 Service Unavailable.
        error_code:  ``"AI_SERVICE_ERROR"``.
    """

    status_code: int = HTTPStatus.SERVICE_UNAVAILABLE.value
    error_code: str = "AI_SERVICE_ERROR"

    def __init__(
        self,
        message: str = "The AI service is currently unavailable.",
        details: Any = None,
    ) -> None:
        """
        Initialise an AI service exception.

        Args:
            message: Human-readable description of the AI failure.
            details: Optional diagnostic context (model name, prompt length,
                     etc.).
        """
        super().__init__(message=message, details=details)
