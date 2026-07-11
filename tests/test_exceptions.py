"""
Exception Hierarchy Tests.

Purpose:
    Verify that every domain exception class is correctly structured,
    carries the right HTTP status code and error code, and that
    ``AppException`` subclasses behave as expected when raised and caught.

Responsibilities:
    - Assert each exception class has the correct ``status_code``.
    - Assert each exception class has the correct ``error_code``.
    - Assert ``message`` and ``details`` are stored on the instance.
    - Assert that all custom exceptions are subclasses of ``AppException``.
    - Assert that the global exception handlers return the canonical error
      envelope with the correct structure, status code, and ``request_id``.
    - Verify logging is called by the handlers (smoke test via live client).

Dependencies:
    - tests.conftest          — shared ``client`` fixture
    - app.core.exceptions     — domain exception hierarchy
    - app.api.schemas.error   — :class:`~app.api.schemas.error.ErrorResponse`

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from fastapi.testclient import TestClient

from app.core.exceptions import (
    AIException,
    AppException,
    InternalServerException,
    ParsingException,
    ResourceNotFoundException,
    ValidationException,
)

# ---------------------------------------------------------------------------
# Unit tests — exception class structure
# ---------------------------------------------------------------------------


class TestAppException:
    """Tests for the base :class:`AppException`."""

    def test_is_exception_subclass(self) -> None:
        """AppException must inherit from the built-in Exception."""
        assert issubclass(AppException, Exception)

    def test_default_status_code(self) -> None:
        """Default status code must be 500."""
        assert AppException.status_code == 500

    def test_default_error_code(self) -> None:
        """Default error code must be 'INTERNAL_ERROR'."""
        assert AppException.error_code == "INTERNAL_ERROR"

    def test_message_stored(self) -> None:
        """Constructor must store the message on the instance."""
        exc = AppException(message="something went wrong")
        assert exc.message == "something went wrong"

    def test_details_none_by_default(self) -> None:
        """Details must default to None when not supplied."""
        exc = AppException(message="oops")
        assert exc.details is None

    def test_details_stored(self) -> None:
        """Constructor must store details when supplied."""
        exc = AppException(message="oops", details={"key": "value"})
        assert exc.details == {"key": "value"}

    def test_str_is_message(self) -> None:
        """str() of the exception must equal the message."""
        exc = AppException(message="test message")
        assert str(exc) == "test message"

    def test_repr_contains_error_code(self) -> None:
        """repr() must contain the error_code."""
        exc = AppException(message="test")
        assert "INTERNAL_ERROR" in repr(exc)


class TestValidationException:
    """Tests for :class:`ValidationException`."""

    def test_is_app_exception_subclass(self) -> None:
        """ValidationException must subclass AppException."""
        assert issubclass(ValidationException, AppException)

    def test_status_code(self) -> None:
        """Status code must be 422."""
        assert ValidationException.status_code == 422

    def test_error_code(self) -> None:
        """Error code must be 'VALIDATION_ERROR'."""
        assert ValidationException.error_code == "VALIDATION_ERROR"

    def test_default_message(self) -> None:
        """Default message must be present and non-empty."""
        exc = ValidationException()
        assert exc.message

    def test_custom_message(self) -> None:
        """Custom message must be stored."""
        exc = ValidationException(message="field 'name' is required")
        assert exc.message == "field 'name' is required"

    def test_details_stored(self) -> None:
        """Details payload must be stored correctly."""
        exc = ValidationException(details=[{"field": "name", "msg": "required"}])
        assert exc.details is not None


class TestResourceNotFoundException:
    """Tests for :class:`ResourceNotFoundException`."""

    def test_is_app_exception_subclass(self) -> None:
        """ResourceNotFoundException must subclass AppException."""
        assert issubclass(ResourceNotFoundException, AppException)

    def test_status_code(self) -> None:
        """Status code must be 404."""
        assert ResourceNotFoundException.status_code == 404

    def test_error_code(self) -> None:
        """Error code must be 'NOT_FOUND'."""
        assert ResourceNotFoundException.error_code == "NOT_FOUND"

    def test_message_contains_resource_and_id(self) -> None:
        """Message must reference both the resource name and its identifier."""
        exc = ResourceNotFoundException(resource="workspace", identifier="ws-123")
        assert "workspace" in exc.message
        assert "ws-123" in exc.message

    def test_resource_stored(self) -> None:
        """Constructor must store the resource name."""
        exc = ResourceNotFoundException(resource="file", identifier=42)
        assert exc.resource == "file"

    def test_identifier_stored(self) -> None:
        """Constructor must store the identifier."""
        exc = ResourceNotFoundException(resource="file", identifier=42)
        assert exc.identifier == 42

    def test_integer_identifier(self) -> None:
        """Integer identifiers must be accepted."""
        exc = ResourceNotFoundException(resource="record", identifier=99)
        assert exc.identifier == 99


class TestInternalServerException:
    """Tests for :class:`InternalServerException`."""

    def test_is_app_exception_subclass(self) -> None:
        """InternalServerException must subclass AppException."""
        assert issubclass(InternalServerException, AppException)

    def test_status_code(self) -> None:
        """Status code must be 500."""
        assert InternalServerException.status_code == 500

    def test_error_code(self) -> None:
        """Error code must be 'INTERNAL_ERROR'."""
        assert InternalServerException.error_code == "INTERNAL_ERROR"

    def test_default_message(self) -> None:
        """Default message must be present."""
        exc = InternalServerException()
        assert exc.message


class TestParsingException:
    """Tests for :class:`ParsingException`."""

    def test_is_app_exception_subclass(self) -> None:
        """ParsingException must subclass AppException."""
        assert issubclass(ParsingException, AppException)

    def test_status_code(self) -> None:
        """Status code must be 422."""
        assert ParsingException.status_code == 422

    def test_error_code(self) -> None:
        """Error code must be 'PARSING_ERROR'."""
        assert ParsingException.error_code == "PARSING_ERROR"

    def test_custom_message(self) -> None:
        """Custom parse-error message must be stored."""
        exc = ParsingException(message="unexpected token at line 42")
        assert "42" in exc.message


class TestAIException:
    """Tests for :class:`AIException`."""

    def test_is_app_exception_subclass(self) -> None:
        """AIException must subclass AppException."""
        assert issubclass(AIException, AppException)

    def test_status_code(self) -> None:
        """Status code must be 503."""
        assert AIException.status_code == 503

    def test_error_code(self) -> None:
        """Error code must be 'AI_SERVICE_ERROR'."""
        assert AIException.error_code == "AI_SERVICE_ERROR"

    def test_default_message(self) -> None:
        """Default message must be present."""
        exc = AIException()
        assert exc.message


# ---------------------------------------------------------------------------
# Integration tests — handler responses via the live test client
# ---------------------------------------------------------------------------


class TestExceptionHandlerIntegration:
    """
    Integration tests for exception handlers using the shared test client.

    These tests exercise the full request/response cycle including
    middleware and exception handler registration.
    """

    def test_404_returns_error_envelope(self, client: TestClient) -> None:
        """A request to an unknown path must return the canonical error envelope."""
        response = client.get("/api/v1/nonexistent-endpoint-xyz")
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
        assert "error" in body
        assert "request_id" in body
        assert "timestamp" in body

    def test_404_error_code(self, client: TestClient) -> None:
        """404 response must carry the 'NOT_FOUND' error code."""
        response = client.get("/api/v1/nonexistent-endpoint-xyz")
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_404_error_has_message(self, client: TestClient) -> None:
        """404 error payload must contain a non-empty message."""
        response = client.get("/api/v1/nonexistent-endpoint-xyz")
        assert response.json()["error"]["message"]

    def test_request_id_in_response_body(self, client: TestClient) -> None:
        """Error response body must include a non-empty request_id."""
        response = client.get("/api/v1/nonexistent-endpoint-xyz")
        body = response.json()
        assert body["request_id"]

    def test_timestamp_in_error_response(self, client: TestClient) -> None:
        """Error response must contain a parseable ISO-8601 timestamp."""
        from datetime import datetime

        response = client.get("/api/v1/nonexistent-endpoint-xyz")
        body = response.json()
        ts = datetime.fromisoformat(body["timestamp"])
        assert isinstance(ts, datetime)

    def test_success_field_is_false_on_error(self, client: TestClient) -> None:
        """The 'success' field must be False for all error responses."""
        response = client.get("/api/v1/nonexistent-endpoint-xyz")
        assert response.json()["success"] is False
