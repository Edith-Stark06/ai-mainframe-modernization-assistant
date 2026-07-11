"""
Request ID Middleware Tests.

Purpose:
    Verify that :class:`app.core.middleware.RequestIDMiddleware` correctly
    injects, propagates, and echoes the UUID4 correlation identifier on
    every HTTP request/response cycle.

Responsibilities:
    - Assert that every response carries an ``X-Request-ID`` header.
    - Assert that the ``X-Request-ID`` value is a valid UUID4.
    - Assert that a client-supplied ``X-Request-ID`` is reused verbatim.
    - Assert that a fresh UUID4 is generated when no header is supplied.
    - Assert that the ``X-Response-Time-Ms`` header is present and numeric.
    - Verify that the request ID surfaces in error response bodies.
    - Verify end-to-end behaviour on nominal (2xx) and error (4xx/5xx) paths.

Dependencies:
    - tests.conftest             — shared ``client`` fixture
    - app.core.middleware        — :class:`~app.core.middleware.RequestIDMiddleware`

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import uuid

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUEST_ID_HEADER = "X-Request-ID"
_RESPONSE_TIME_HEADER = "X-Response-Time-Ms"

# A known endpoint that returns 200 — used for nominal-path tests.
_HEALTH_PATH = "/api/v1/health"

# A path that does not exist — used for error-path tests.
_MISSING_PATH = "/api/v1/does-not-exist"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _is_valid_uuid4(value: str) -> bool:
    """
    Return True if *value* is a syntactically valid UUID4 string.

    Args:
        value: The string to validate.

    Returns:
        ``True`` if the string is a UUID4, ``False`` otherwise.
    """
    try:
        parsed = uuid.UUID(value, version=4)
        return str(parsed) == value.lower()
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Middleware tests — nominal path (200)
# ---------------------------------------------------------------------------


class TestRequestIDMiddlewareNominalPath:
    """Tests for request ID injection on successful (2xx) responses."""

    def test_response_contains_request_id_header(self, client: TestClient) -> None:
        """Every 200 response must carry an X-Request-ID header."""
        response = client.get(_HEALTH_PATH)
        assert _REQUEST_ID_HEADER in response.headers

    def test_auto_generated_request_id_is_uuid4(self, client: TestClient) -> None:
        """Auto-generated request ID must be a valid UUID4."""
        response = client.get(_HEALTH_PATH)
        request_id = response.headers[_REQUEST_ID_HEADER]
        assert _is_valid_uuid4(request_id), f"Not a valid UUID4: {request_id!r}"

    def test_client_supplied_request_id_is_reused(self, client: TestClient) -> None:
        """A client-supplied X-Request-ID must be echoed back unchanged."""
        custom_id = str(uuid.uuid4())
        response = client.get(
            _HEALTH_PATH,
            headers={_REQUEST_ID_HEADER: custom_id},
        )
        assert response.headers[_REQUEST_ID_HEADER] == custom_id

    def test_different_requests_get_unique_ids(self, client: TestClient) -> None:
        """Consecutive requests without a supplied ID must receive unique UUIDs."""
        id1 = client.get(_HEALTH_PATH).headers[_REQUEST_ID_HEADER]
        id2 = client.get(_HEALTH_PATH).headers[_REQUEST_ID_HEADER]
        assert id1 != id2

    def test_response_contains_timing_header(self, client: TestClient) -> None:
        """Every response must carry an X-Response-Time-Ms header."""
        response = client.get(_HEALTH_PATH)
        assert _RESPONSE_TIME_HEADER in response.headers

    def test_timing_header_is_numeric(self, client: TestClient) -> None:
        """X-Response-Time-Ms must be convertible to a float."""
        response = client.get(_HEALTH_PATH)
        elapsed = float(response.headers[_RESPONSE_TIME_HEADER])
        assert elapsed >= 0.0

    def test_timing_header_is_reasonable(self, client: TestClient) -> None:
        """X-Response-Time-Ms must be less than 5 000 ms for in-process tests."""
        response = client.get(_HEALTH_PATH)
        elapsed = float(response.headers[_RESPONSE_TIME_HEADER])
        assert elapsed < 5_000.0


# ---------------------------------------------------------------------------
# Middleware tests — error path (4xx)
# ---------------------------------------------------------------------------


class TestRequestIDMiddlewareErrorPath:
    """Tests for request ID injection on error (4xx) responses."""

    def test_404_response_contains_request_id_header(self, client: TestClient) -> None:
        """404 responses must still carry an X-Request-ID header."""
        response = client.get(_MISSING_PATH)
        assert _REQUEST_ID_HEADER in response.headers

    def test_404_request_id_is_uuid4(self, client: TestClient) -> None:
        """Request ID on 404 responses must be a valid UUID4."""
        response = client.get(_MISSING_PATH)
        request_id = response.headers[_REQUEST_ID_HEADER]
        assert _is_valid_uuid4(request_id), f"Not a valid UUID4: {request_id!r}"

    def test_client_supplied_id_echoed_on_404(self, client: TestClient) -> None:
        """A client-supplied X-Request-ID must be echoed on 404 responses."""
        custom_id = str(uuid.uuid4())
        response = client.get(
            _MISSING_PATH,
            headers={_REQUEST_ID_HEADER: custom_id},
        )
        assert response.headers[_REQUEST_ID_HEADER] == custom_id

    def test_request_id_header_matches_body_on_error(self, client: TestClient) -> None:
        """
        The X-Request-ID response header must match the request_id in the
        error response JSON body.
        """
        custom_id = str(uuid.uuid4())
        response = client.get(
            _MISSING_PATH,
            headers={_REQUEST_ID_HEADER: custom_id},
        )
        body = response.json()
        assert body["request_id"] == custom_id
        assert response.headers[_REQUEST_ID_HEADER] == custom_id

    def test_404_response_contains_timing_header(self, client: TestClient) -> None:
        """404 responses must carry an X-Response-Time-Ms header."""
        response = client.get(_MISSING_PATH)
        assert _RESPONSE_TIME_HEADER in response.headers


# ---------------------------------------------------------------------------
# Middleware tests — root endpoint
# ---------------------------------------------------------------------------


class TestRequestIDMiddlewareRootEndpoint:
    """Tests for middleware behaviour on the application root endpoint."""

    def test_root_response_contains_request_id_header(self, client: TestClient) -> None:
        """GET / must include X-Request-ID in the response headers."""
        response = client.get("/")
        assert _REQUEST_ID_HEADER in response.headers

    def test_root_response_contains_timing_header(self, client: TestClient) -> None:
        """GET / must include X-Response-Time-Ms in the response headers."""
        response = client.get("/")
        assert _RESPONSE_TIME_HEADER in response.headers

    def test_root_request_id_is_uuid4(self, client: TestClient) -> None:
        """Request ID on GET / must be a valid UUID4."""
        response = client.get("/")
        request_id = response.headers[_REQUEST_ID_HEADER]
        assert _is_valid_uuid4(request_id)
