"""
Request ID Middleware.

Purpose:
    Inject a unique UUID4 correlation identifier into every HTTP request
    and propagate it in the response headers so that distributed logs can
    be correlated end-to-end.

Responsibilities:
    - Generate a UUID4 ``X-Request-ID`` for each incoming request if one
      is not already present in the request headers.
    - Store the identifier in ``request.state.request_id`` so that route
      handlers and exception handlers can access it without parsing
      headers manually.
    - Append ``X-Request-ID`` and ``X-Response-Time-Ms`` to every outgoing
      response.
    - Log the start and end of each request at DEBUG level with the
      correlation identifier and response time.

Dependencies:
    - starlette — :class:`~starlette.middleware.base.BaseHTTPMiddleware`,
                  :class:`~starlette.requests.Request`,
                  :class:`~starlette.responses.Response`
    - loguru    — :data:`~loguru._logger.Logger`

Examples:
    Registering the middleware on the FastAPI application::

        from fastapi import FastAPI
        from app.core.middleware import RequestIDMiddleware

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import logger

__all__ = ["RequestIDMiddleware"]

_REQUEST_ID_HEADER = "X-Request-ID"
_RESPONSE_TIME_HEADER = "X-Response-Time-Ms"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that assigns a UUID4 correlation ID to every request.

    Behaviour
    ---------
    * If the incoming request already carries an ``X-Request-ID`` header
      the value is reused; otherwise a fresh UUID4 is generated.
    * The request ID is stored in ``request.state.request_id`` and
      echoed back in the ``X-Request-ID`` response header.
    * Response time in milliseconds is appended as ``X-Response-Time-Ms``.
    * Both the inbound and outbound events are logged at DEBUG level.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Process an HTTP request through the middleware pipeline.

        Args:
            request:   The incoming Starlette/FastAPI request.
            call_next: Callable that invokes the next layer in the ASGI
                       stack (route handler or next middleware).

        Returns:
            The response with ``X-Request-ID`` and
            ``X-Response-Time-Ms`` headers attached.
        """
        # ------------------------------------------------------------------
        # Resolve or generate the correlation ID
        # ------------------------------------------------------------------
        request_id: str = request.headers.get(
            _REQUEST_ID_HEADER,
            str(uuid.uuid4()),
        )
        request.state.request_id = request_id

        logger.debug(
            "Request started | request_id={} | method={} | path={}",
            request_id,
            request.method,
            request.url.path,
        )

        # ------------------------------------------------------------------
        # Delegate to the next handler and measure elapsed time
        # ------------------------------------------------------------------
        start_ns: int = time.perf_counter_ns()
        response: Response = await call_next(request)
        elapsed_ms: float = (time.perf_counter_ns() - start_ns) / 1_000_000

        # ------------------------------------------------------------------
        # Attach correlation and timing headers to the response
        # ------------------------------------------------------------------
        response.headers[_REQUEST_ID_HEADER] = request_id
        response.headers[_RESPONSE_TIME_HEADER] = f"{elapsed_ms:.3f}"

        logger.debug(
            "Request completed | request_id={} | method={} | path={} | status={} | elapsed_ms={:.3f}",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response
