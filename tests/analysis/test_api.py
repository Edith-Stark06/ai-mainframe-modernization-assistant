"""
Analysis API Endpoint Tests.

Purpose:
    Integration tests for the ``POST /api/v1/workspaces/{workspace_id}/analyze``
    endpoint.

    Tests exercise the full request/response cycle through the FastAPI
    test client against real temporary workspace directories and the
    production AnalysisService.

Coverage:
    - Successful analysis of a valid COBOL source file.
    - AST serialization in response.
    - IR serialization in response.
    - Java source in response.
    - Diagnostics in response.
    - JSON-safe response structure.
    - Missing workspace handling.
    - Missing source file handling.
    - Unsupported file extension handling.
    - Analysis failure handling.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

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

_COBOL_UNDEFINED = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. UNDEFINED-VAR.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            MOVE 5 TO WS-UNDEFINED.
            DISPLAY WS-UNDEFINED.
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
        (ws_dir / filename).write_bytes(content)
    return ws_id


# ---------------------------------------------------------------------------
# Nominal — successful analysis
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointNominal:
    """Tests for successful analysis responses."""

    def test_analyze_returns_200(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Analysis endpoint must return HTTP 200 for a valid request."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        )
        assert response.status_code == 200

    def test_analyze_success_is_true(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """success field must be True for a successful analysis."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["success"] is True

    def test_analyze_workspace_id_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """workspace_id in the response must match the request path parameter."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["workspace_id"] == ws_id

    def test_analyze_filename_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """filename in the response must match the requested filename."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["filename"] == "hello.cbl"

    def test_analyze_returns_java_source(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Java source must be present in the response."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert "public class" in body["java_source"]

    def test_analyze_returns_ast(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """AST must be present in the response for successful analysis."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["ast"] is not None
        assert body["ast"]["type"] == "ProgramNode"

    def test_analyze_returns_ir(self, client: TestClient, workspace_root: Path) -> None:
        """IR must be present in the response for successful analysis."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["ir"] is not None
        assert body["ir"]["type"] == "IRProgram"

    def test_analyze_returns_diagnostics(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Diagnostics list must be present (may be empty on success)."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert "diagnostics" in body
        assert isinstance(body["diagnostics"], list)

    def test_analyze_response_is_json_safe(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """All values in the response must be JSON-safe."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        _assert_json_safe(body)

    def test_analyze_error_is_none_on_success(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """error must be None for a successful analysis."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["error"] is None


# ---------------------------------------------------------------------------
# Diagnostics path
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointDiagnostics:
    """Tests for analysis responses that include compiler diagnostics."""

    def test_analyze_with_semantic_error_returns_failure(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A file with semantic errors must return success=False."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()
        assert body["success"] is False

    def test_analyze_with_semantic_error_has_diagnostics(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A file with semantic errors must return diagnostics."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()
        assert len(body["diagnostics"]) > 0

    def test_analyze_with_semantic_error_has_error(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A failed analysis should have success=False and diagnostics."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()
        assert body["success"] is False
        assert len(body["diagnostics"]) > 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointErrors:
    """Tests for error responses from the analysis endpoint."""

    def test_analyze_missing_workspace_returns_404(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A non-existent workspace must return HTTP 404."""
        response = client.post(
            "/api/v1/workspaces/nonexistent-ws/analyze",
            json={"filename": "prog.cbl"},
        )
        assert response.status_code == 404

    def test_analyze_missing_workspace_error_envelope(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """404 response must follow the canonical error envelope."""
        body = client.post(
            "/api/v1/workspaces/ghost-ws/analyze",
            json={"filename": "prog.cbl"},
        ).json()
        assert body["success"] is False
        assert "error" in body

    def test_analyze_missing_source_returns_404(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A non-existent source file must return HTTP 404."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "missing.cbl"},
        )
        assert response.status_code == 404

    def test_analyze_unsupported_extension_returns_422(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """An unsupported file extension must return HTTP 422."""
        ws_id = _create_workspace(workspace_root, {"readme.txt": b"hello"})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "readme.txt"},
        )
        assert response.status_code == 422

    def test_analyze_path_traversal_blocked(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Path traversal attempts must be rejected."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "../../../etc/passwd"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# JSON-safe helper
# ---------------------------------------------------------------------------


def _assert_json_safe(value: object) -> None:
    """Recursively verify that *value* contains only JSON-native types."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_safe(item)
        return
    if isinstance(value, dict):
        for v in value.values():
            _assert_json_safe(v)
        return
    raise TypeError(f"Non-JSON-safe value: {type(value).__name__}")
