"""
Health Endpoint Tests.

Purpose:
    Verify that the health-check endpoint and the application root
    endpoint behave correctly under nominal conditions.

Responsibilities:
    - Assert ``GET /`` returns HTTP 200 with the expected JSON keys.
    - Assert ``GET /api/v1/health`` returns HTTP 200 with all required
      fields and correct types.
    - Assert the OpenAPI documentation endpoint (``GET /docs``) is
      reachable.
    - Validate the structure and content of the :class:`HealthResponse`
      payload.

Dependencies:
    - tests.conftest — shared ``client`` fixture
    - app.core.config — settings for assertion values

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------


class TestRootEndpoint:
    """Tests for ``GET /``."""

    def test_root_returns_http_200(self, client: TestClient) -> None:
        """Root endpoint must return HTTP 200."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_json(self, client: TestClient) -> None:
        """Root endpoint response must be valid JSON."""
        response = client.get("/")
        assert response.headers["content-type"].startswith("application/json")

    def test_root_contains_application(self, client: TestClient) -> None:
        """Root endpoint JSON must contain an 'application' key."""
        response = client.get("/")
        payload = response.json()
        assert "application" in payload
        assert payload["application"] == settings.app_name

    def test_root_contains_status(self, client: TestClient) -> None:
        """Root endpoint JSON must contain a 'status' key set to 'running'."""
        response = client.get("/")
        payload = response.json()
        assert "status" in payload
        assert payload["status"] == "running"

    def test_root_contains_docs_link(self, client: TestClient) -> None:
        """Root endpoint JSON must contain a 'docs' key pointing to /docs."""
        response = client.get("/")
        payload = response.json()
        assert "docs" in payload
        assert payload["docs"] == "/docs"

    def test_root_contains_health_link(self, client: TestClient) -> None:
        """Root endpoint JSON must contain a 'health' key."""
        response = client.get("/")
        payload = response.json()
        assert "health" in payload

    def test_root_contains_version(self, client: TestClient) -> None:
        """Root endpoint JSON must contain the application version."""
        response = client.get("/")
        payload = response.json()
        assert "version" in payload
        assert payload["version"] == settings.app_version


# ---------------------------------------------------------------------------
# Docs endpoint
# ---------------------------------------------------------------------------


class TestDocsEndpoint:
    """Tests for ``GET /docs``."""

    def test_docs_returns_http_200(self, client: TestClient) -> None:
        """Swagger UI documentation endpoint must return HTTP 200."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_docs_returns_html(self, client: TestClient) -> None:
        """Swagger UI must return an HTML page."""
        response = client.get("/docs")
        assert "text/html" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for ``GET /api/v1/health``."""

    def test_health_returns_http_200(self, client: TestClient) -> None:
        """Health endpoint must return HTTP 200."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client: TestClient) -> None:
        """Health endpoint must return valid JSON."""
        response = client.get("/api/v1/health")
        assert response.headers["content-type"].startswith("application/json")

    def test_health_status_is_healthy(self, client: TestClient) -> None:
        """Health response must report ``status`` as ``'healthy'``."""
        response = client.get("/api/v1/health")
        payload = response.json()
        assert payload["status"] == "healthy"

    def test_health_application_name(self, client: TestClient) -> None:
        """Health response must report the correct application name."""
        response = client.get("/api/v1/health")
        payload = response.json()
        assert payload["application"] == settings.app_name

    def test_health_version(self, client: TestClient) -> None:
        """Health response must report the correct application version."""
        response = client.get("/api/v1/health")
        payload = response.json()
        assert payload["version"] == settings.app_version

    def test_health_timestamp_present(self, client: TestClient) -> None:
        """Health response must contain a ``timestamp`` field."""
        response = client.get("/api/v1/health")
        payload = response.json()
        assert "timestamp" in payload

    def test_health_timestamp_is_valid_iso8601(self, client: TestClient) -> None:
        """Health response timestamp must be a parseable ISO 8601 string."""
        response = client.get("/api/v1/health")
        payload = response.json()
        # Raises ValueError if not a valid datetime string — that is the
        # assertion: parsing must succeed without raising.
        timestamp = datetime.fromisoformat(payload["timestamp"])
        assert isinstance(timestamp, datetime)

    def test_health_response_schema(self, client: TestClient) -> None:
        """Health response must contain exactly the expected top-level keys."""
        response = client.get("/api/v1/health")
        payload = response.json()
        expected_keys = {"status", "application", "version", "timestamp"}
        assert expected_keys == set(payload.keys())

    @pytest.mark.parametrize(
        "method",
        ["POST", "PUT", "PATCH", "DELETE"],
    )
    def test_health_unsupported_methods_return_405(
        self, client: TestClient, method: str
    ) -> None:
        """Health endpoint must reject non-GET HTTP methods with 405."""
        response = client.request(method, "/api/v1/health")
        assert response.status_code == 405
