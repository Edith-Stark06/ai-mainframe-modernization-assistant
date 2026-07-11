"""
Global Exception Handlers.

Purpose:
    Register FastAPI exception handlers that intercept every unhandled
    exception and serialise it into the canonical error envelope defined
    in :mod:`app.api.schemas.error`.

Responsibilities:
    - Handle :class:`app.core.exceptions.AppException` subclasses and map
      them to their declared HTTP status codes.
    - Handle FastAPI's :class:`fastapi.exceptions.RequestValidationError`
      and produce a 422 response with field-level detail.
    - Handle Starlette's :class:`starlette.exceptions.HTTPException` for
      standard 404 / 405 / etc. responses.
    - Handle all remaining :class:`Exception` instances as 500 errors.
    - Log every exception with Loguru at the appropriate level.
    - Extract the ``X-Request-ID`` header set by
      :class:`app.core.middleware.RequestIDMiddleware`.

Dependencies:
    - fastapi                  — :class:`~fastapi.FastAPI`,
                                 :class:`~fastapi.exceptions.RequestValidationError`
    - starlette                — :class:`~starlette.exceptions.HTTPException`,
                                 :class:`~starlette.requests.Request`,
                                 :class:`~starlette.responses.JSONResponse`
    - app.core.exceptions      — domain exception hierarchy
    - app.api.schemas.error    — :class:`~app.api.schemas.error.ErrorResponse`
    - app.core.logging         — Loguru logger

Examples:
    Registering handlers on the FastAPI application::

        from app.core.handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas.error import ErrorDetail, ErrorResponse
from app.core.exceptions import AppException
from app.core.logging import logger

__all__ = ["register_exception_handlers"]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REQUEST_ID_HEADER = "X-Request-ID"
_UNKNOWN_REQUEST_ID = "unknown"


def _get_request_id(request: Request) -> str:
    """
    Return the request correlation ID.

    The RequestIDMiddleware stores the generated UUID in
    request.state.request_id. If the middleware was not executed,
    fall back to the incoming header and finally to "unknown".
    """
    return getattr(
        request.state,
        "request_id",
        request.headers.get(_REQUEST_ID_HEADER, _UNKNOWN_REQUEST_ID),
    )


def _build_json_response(body: ErrorResponse, status_code: int) -> JSONResponse:
    """
    Serialise an :class:`ErrorResponse` into a :class:`JSONResponse`.

    Args:
        body:        The populated error envelope.
        status_code: HTTP status code to set on the response.

    Returns:
        A :class:`~fastapi.responses.JSONResponse` with the serialised body.
    """
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Individual handlers
# ---------------------------------------------------------------------------


async def _handle_app_exception(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    """
    Handle any :class:`app.core.exceptions.AppException` subclass.

    Logs at WARNING level for client errors (4xx) and at ERROR level for
    server errors (5xx), then returns the canonical error envelope.

    Args:
        request: The incoming HTTP request.
        exc:     The raised domain exception.

    Returns:
        A JSON error response with the exception's declared status code.
    """
    request_id = _get_request_id(request)
    log_msg = "AppException | request_id={} | code={} | status={} | message={}"
    if exc.status_code >= 500:
        logger.error(log_msg, request_id, exc.error_code, exc.status_code, exc.message)
    else:
        logger.warning(
            log_msg, request_id, exc.error_code, exc.status_code, exc.message
        )

    body = ErrorResponse(
        error=ErrorDetail(
            code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
        request_id=request_id,
    )
    return _build_json_response(body, exc.status_code)


async def _handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Handle Pydantic / FastAPI request-body validation errors (422).

    The ``details`` field is populated with the structured validation
    errors produced by Pydantic v2 so clients can identify which fields
    are invalid.

    Args:
        request: The incoming HTTP request.
        exc:     The FastAPI validation error.

    Returns:
        A 422 JSON error response with field-level error details.
    """
    request_id = _get_request_id(request)
    errors = exc.errors()
    logger.warning(
        "RequestValidationError | request_id={} | errors={}",
        request_id,
        errors,
    )

    body = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details=errors,
        ),
        request_id=request_id,
    )
    return _build_json_response(body, 422)


async def _handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """
    Handle standard Starlette / FastAPI HTTP exceptions (404, 405, etc.).

    Args:
        request: The incoming HTTP request.
        exc:     The Starlette HTTP exception.

    Returns:
        A JSON error response with the exception's status code.
    """
    request_id = _get_request_id(request)
    logger.warning(
        "HTTPException | request_id={} | status={} | detail={}",
        request_id,
        exc.status_code,
        exc.detail,
    )

    # Map common status codes to machine-readable codes.
    code_map: dict[int, str] = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        429: "TOO_MANY_REQUESTS",
    }
    error_code = code_map.get(exc.status_code, "HTTP_ERROR")

    body = ErrorResponse(
        error=ErrorDetail(
            code=error_code,
            message=str(exc.detail),
            details=None,
        ),
        request_id=request_id,
    )
    return _build_json_response(body, exc.status_code)


async def _handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Handle any exception not caught by a more specific handler (500).

    Logs the full traceback at ERROR level so operators can diagnose
    unexpected failures without exposing internals to the client.

    Args:
        request: The incoming HTTP request.
        exc:     The unhandled exception.

    Returns:
        A 500 JSON error response with a generic message.
    """
    request_id = _get_request_id(request)
    logger.exception(
        "Unhandled exception | request_id={} | type={} | message={}",
        request_id,
        type(exc).__name__,
        str(exc),
    )

    body = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
            details=None,
        ),
        request_id=request_id,
    )
    return _build_json_response(body, 500)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_exception_handlers(application: FastAPI) -> None:
    """
    Register all global exception handlers on the FastAPI application.

    Handlers are evaluated in specificity order: domain exceptions first,
    then FastAPI validation errors, then generic HTTP exceptions, and
    finally a catch-all for any unhandled ``Exception``.

    Args:
        application: The :class:`~fastapi.FastAPI` instance to configure.

    Examples:
        ::

            from fastapi import FastAPI
            from app.core.handlers import register_exception_handlers

            app = FastAPI()
            register_exception_handlers(app)
    """
    application.add_exception_handler(AppException, _handle_app_exception)  # type: ignore[arg-type]
    application.add_exception_handler(
        RequestValidationError, _handle_request_validation_error  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        StarletteHTTPException, _handle_http_exception  # type: ignore[arg-type]
    )
    application.add_exception_handler(Exception, _handle_unhandled_exception)  # type: ignore[arg-type]

    logger.info("Global exception handlers registered.")
