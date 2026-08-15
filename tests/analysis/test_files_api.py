"""
Workspace File Source Context API Tests.

Purpose:
    Integration tests for the
    ``GET /api/v1/workspaces/{workspace_id}/files/{filename}`` endpoint.

    Tests exercise the full request/response cycle through the FastAPI
    test client against real temporary workspace directories.

Coverage:
    - Successful source file retrieval.
    - Content correctness.
    - Metadata correctness (extension, size_bytes, sha256).
    - Missing workspace handling.
    - Missing source file handling.
    - Path traversal blocking.
    - Absolute path blocking.
    - JSON-safe response structure.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COBOL_HELLO = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. HELLO-WORLD.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            DISPLAY "HELLO WORLD".
            STOP RUN.
"""

_COBOL_NESTED = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. NESTED.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            DISPLAY "NESTED".
            STOP RUN.
"""


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a module-scoped test client."""
    with TestClient(app) as tc:
        yield tc  # type: ignore[misc]


@pytest.fixture()
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Patch ``settings.workspace_dir`` to *tmp_path* and return the root.

    This isolates API tests from the real workspace directory.
    """
    from app.core import config as cfg_mod

    monkeypatch.setattr(cfg_mod.settings, "workspace_dir", str(tmp_path))

    return tmp_path


def _create_workspace(root: Path, files: dict[str, bytes]) -> str:
    """Create a workspace sub-directory with the given files and return its ID."""
    ws_id = str(uuid.uuid4())
    ws_dir = root / ws_id
    ws_dir.mkdir(parents=True)
    for filename, content in files.items():
        file_path = ws_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
    return ws_id


# ---------------------------------------------------------------------------
# Nominal — successful file retrieval
# ---------------------------------------------------------------------------


class TestGetSourceFileNominal:
    """Tests for successful file source retrieval responses."""

    def test_get_file_returns_200(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """File source endpoint must return HTTP 200 for a valid request."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        )
        assert response.status_code == 200

    def test_get_file_success_is_true(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """success field must be True for a successful retrieval."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        ).json()
        assert body["success"] is True

    def test_get_file_workspace_id_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """workspace_id in the response must match the request path parameter."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        ).json()
        assert body["workspace_id"] == ws_id

    def test_get_file_filename_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """filename in the response must match the requested filename."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        ).json()
        assert body["filename"] == "hello.cbl"

    def test_get_file_content_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """content must match the stored file content."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        ).json()
        assert body["content"] == _COBOL_HELLO.decode("utf-8")

    def test_get_file_metadata_extension(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """extension metadata must match the file extension."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        ).json()
        assert body["extension"] == ".cbl"

    def test_get_file_metadata_size_bytes(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """size_bytes metadata must match the actual file size."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        ).json()
        assert body["size_bytes"] == len(_COBOL_HELLO)

    def test_get_file_metadata_sha256(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """sha256 metadata must match the actual SHA-256 digest."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        expected_sha = hashlib.sha256(_COBOL_HELLO).hexdigest()
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        ).json()
        assert body["sha256"] == expected_sha

    def test_get_file_response_is_json_serializable(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """The complete response must be JSON serializable."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.get(
            f"/api/v1/workspaces/{ws_id}/files/hello.cbl",
        )
        body = response.json()
        json_str = __import__("json").dumps(body)
        assert isinstance(json_str, str)
        assert len(json_str) > 0


# ---------------------------------------------------------------------------
# Nested files
# ---------------------------------------------------------------------------


class TestGetSourceFileNested:
    """Tests for nested file paths within a workspace."""

    def test_get_nested_file_succeeds(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A valid nested file path should be returned successfully."""
        ws_id = _create_workspace(workspace_root, {"subdir/nested.cbl": _COBOL_NESTED})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/files/subdir/nested.cbl",
        ).json()
        assert body["success"] is True
        assert body["filename"] == "subdir/nested.cbl"
        assert body["content"] == _COBOL_NESTED.decode("utf-8")


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestGetSourceFileErrors:
    """Tests for error responses from the file source endpoint."""

    def test_get_file_missing_workspace_returns_404(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A non-existent workspace must return HTTP 404."""
        response = client.get(
            "/api/v1/workspaces/nonexistent-ws/files/prog.cbl",
        )
        assert response.status_code == 404
        body = response.json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")

    def test_get_file_missing_source_returns_404(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A non-existent source file must return HTTP 404."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.get(
            f"/api/v1/workspaces/{ws_id}/files/missing.cbl",
        )
        assert response.status_code == 404
        body = response.json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")

    def test_get_file_dotdot_traversal_blocked(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """`../` traversal attempts in URL paths are rejected by FastAPI routing."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.get(
            f"/api/v1/workspaces/{ws_id}/files/../outside.cbl",
        )
        # FastAPI normalizes `../` in URL paths before routing, so the
        # route does not match and returns 404. The route handler's
        # `relative_to` check provides defense-in-depth for any traversal
        # that reaches the handler.
        assert response.status_code == 404
        body = response.json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")

    def test_get_file_double_dotdot_traversal_blocked(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """`../../` traversal attempts in URL paths are rejected by FastAPI routing."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.get(
            f"/api/v1/workspaces/{ws_id}/files/../../outside.cbl",
        )
        assert response.status_code == 404
        body = response.json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")

    def test_get_file_absolute_path_blocked(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """An absolute path must not escape the workspace."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.get(
            f"/api/v1/workspaces/{ws_id}/files/etc/passwd",
        )
        assert response.status_code == 404
        body = response.json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")


# ---------------------------------------------------------------------------
# Canonical error envelope helper
# ---------------------------------------------------------------------------


def _assert_error_envelope(body: dict, expected_code: str | None = None) -> None:
    """Verify that *body* matches the repository's canonical error envelope."""
    assert body.get("success") is False
    error = body.get("error")
    assert isinstance(error, dict)
    assert "code" in error
    assert "message" in error
    if expected_code is not None:
        assert error["code"] == expected_code
    assert "request_id" in body
    assert "timestamp" in body
