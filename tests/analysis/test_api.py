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

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.schemas.analysis import AnalysisResponse
from app.main import app
from app.workspace.inventory import InventoryBuilder

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

_COBOL_WITH_CALL = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. CALL-TEST.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            CALL "CUSTOMER-SERVICE".
            STOP RUN.
"""

_COBOL_WITH_PERFORM = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. PERFORM-TEST.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            PERFORM CALCULATE-BONUS.
            STOP RUN.
"""

_COBOL_WITH_MULTIPLE_DEPS = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. MULTI-DEPS.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            PERFORM INIT-RTN
            CALL SUBPROG.
        INIT-RTN.
            DISPLAY "INIT".
"""

_COBOL_WITH_DUPLICATES = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. DUP-TEST.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            CALL BONUSMOD
            CALL BONUSMOD
            PERFORM WORK
            PERFORM WORK.
"""

_COBOL_UNDEFINED = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. UNDEFINED-VAR.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            MOVE 5 TO WS-UNDEFINED.
            DISPLAY WS-UNDEFINED.
            STOP RUN.
"""

_COBOL_SYNTAX_ERROR = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. SYNTAX-ERR.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            INVALID SYNTAX HERE
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

    def test_analyze_status_is_success(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """status field must be SUCCESS for a successful analysis."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["status"] == "SUCCESS"

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

    def test_analyze_returns_analysis_id(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """analysis_id must be present in the response."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert "analysis_id" in body
        assert isinstance(body["analysis_id"], str)

    def test_analyze_analysis_id_is_uuid4(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """analysis_id must parse as a valid UUID version 4."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        val = uuid.UUID(body["analysis_id"])
        assert val.version == 4

    def test_analyze_analysis_id_is_unique(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """analysis_id must be unique across independent requests."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body1 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        body2 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body1["analysis_id"] != body2["analysis_id"]

    def test_analyze_returns_source_metadata(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """source_metadata must be present and correctly populated."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})

        inventory_builder = InventoryBuilder()
        inventory = inventory_builder.build(ws_id, workspace_root / ws_id)
        inventory_file = next(f for f in inventory.files if f.filename == "hello.cbl")

        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()

        assert "source_metadata" in body
        metadata = body["source_metadata"]

        assert metadata["extension"] == inventory_file.extension
        assert metadata["size_bytes"] == inventory_file.size_bytes
        assert metadata["sha256"] == inventory_file.sha256

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

    def test_analyze_returns_dependencies(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Dependencies must be accurately extracted and serialized."""
        ws_id = _create_workspace(
            workspace_root,
            {"hello.cbl": _COBOL_HELLO, "call_test.cbl": _COBOL_WITH_CALL},
        )

        # Test no dependencies
        body_no_deps = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body_no_deps["dependencies"] == []

        # Test with CALL dependency
        body_with_deps = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "call_test.cbl"},
        ).json()
        deps = body_with_deps["dependencies"]
        assert len(deps) == 1
        assert deps[0]["type"] == "CALL"
        assert deps[0]["target"] == '"CUSTOMER-SERVICE"'

        loc = deps[0]["source_location"]
        assert loc["type"] == "Position"
        assert loc["line"] == 6
        assert loc["column"] == 13
        assert "offset" in loc
        assert "filename" in loc

    def test_analyze_returns_perform_dependency(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """PERFORM dependencies must be accurately extracted and serialized."""
        ws_id = _create_workspace(
            workspace_root,
            {"perform_test.cbl": _COBOL_WITH_PERFORM},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "perform_test.cbl"},
        ).json()
        deps = body["dependencies"]
        assert len(deps) == 1
        assert deps[0]["type"] == "PERFORM"
        assert deps[0]["target"] == "CALCULATE-BONUS"
        loc = deps[0]["source_location"]
        assert loc["type"] == "Position"
        assert loc["line"] == 6
        assert loc["column"] == 13
        assert "offset" in loc
        assert "filename" in loc

    def test_analyze_returns_multiple_dependencies(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Multiple dependencies must be returned in deterministic order."""
        ws_id = _create_workspace(
            workspace_root,
            {"multi.cbl": _COBOL_WITH_MULTIPLE_DEPS},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "multi.cbl"},
        ).json()
        deps = body["dependencies"]
        assert len(deps) == 2
        assert deps[0]["type"] == "PERFORM"
        assert deps[0]["target"] == "INIT-RTN"
        assert deps[1]["type"] == "CALL"
        assert deps[1]["target"] == "SUBPROG"

    def test_analyze_deduplicates_dependencies(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Duplicate dependencies must be deduplicated, preserving first occurrence."""
        ws_id = _create_workspace(
            workspace_root,
            {"dup.cbl": _COBOL_WITH_DUPLICATES},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "dup.cbl"},
        ).json()
        deps = body["dependencies"]
        assert len(deps) == 2
        assert deps[0]["type"] == "CALL"
        assert deps[0]["target"] == "BONUSMOD"
        assert deps[0]["source_location"]["line"] == 6
        assert deps[1]["type"] == "PERFORM"
        assert deps[1]["target"] == "WORK"
        assert deps[1]["source_location"]["line"] == 8

    def test_analyze_dependency_response_schema_validation(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """The response must conform to the typed DependencyResponse schema."""
        from app.api.schemas.dependencies import DependencyResponse

        ws_id = _create_workspace(
            workspace_root,
            {"call_test.cbl": _COBOL_WITH_CALL},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "call_test.cbl"},
        ).json()
        for dep in body["dependencies"]:
            validated = DependencyResponse.model_validate(dep)
            assert validated.type in {"CALL", "PERFORM"}
            assert isinstance(validated.target, str)
            if validated.source_location is not None:
                assert validated.source_location.line >= 1
                assert validated.source_location.column >= 1
                assert validated.source_location.offset >= 0
                assert isinstance(validated.source_location.filename, str)

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

    def test_analyze_response_is_json_serializable(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """The complete successful response must be JSON serializable."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        )
        body = response.json()
        json_str = json.dumps(body)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

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

    def test_analyze_response_matches_pydantic_schema(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """The response must strictly conform to AnalysisResponse."""

        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        # model_validate will raise ValidationError if it doesn't match
        validated = AnalysisResponse.model_validate(body)
        assert validated.success is True
        assert validated.filename == "hello.cbl"


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
        """A failed analysis should have success=False, diagnostics, and a valid analysis_id."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()
        assert body["success"] is False
        assert len(body["diagnostics"]) > 0
        assert "analysis_id" in body
        val = uuid.UUID(body["analysis_id"])
        assert val.version == 4

    def test_analyze_with_semantic_error_preserves_ast_and_ir(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """AST and IR must be preserved in the response even if semantic analysis fails."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()
        assert body["success"] is False
        assert body["ast"] is not None, "AST must be preserved on semantic error"
        assert body["ast"]["type"] == "ProgramNode"

        assert body["ir"] is not None, "IR must be preserved on semantic error"
        assert body["ir"]["type"] == "IRProgram"

    def test_analyze_with_semantic_error_preserves_source_metadata(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """source_metadata must be preserved on semantic error."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})

        inventory_builder = InventoryBuilder()
        inventory = inventory_builder.build(ws_id, workspace_root / ws_id)
        inventory_file = next(
            f for f in inventory.files if f.filename == "undefined.cbl"
        )

        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()

        assert body["success"] is False
        assert "source_metadata" in body
        metadata = body["source_metadata"]

        assert metadata["extension"] == inventory_file.extension
        assert metadata["size_bytes"] == inventory_file.size_bytes
        assert metadata["sha256"] == inventory_file.sha256

    def test_analyze_with_analysis_service_failure_has_analysis_id(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure within AnalysisService (e.g. exception) must still return a valid analysis_id."""

        from app.analysis.models import AnalysisResult

        def mock_analyze_file(*args, **kwargs) -> AnalysisResult:
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=False,
                error=Exception("Simulated internal compiler crash"),
                dependencies=[],
                ast=None,
                ir=None,
            )

        monkeypatch.setattr(
            "app.api.routers.analysis.AnalysisService.analyze_file", mock_analyze_file
        )

        ws_id = _create_workspace(workspace_root, {"syntax.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "syntax.cbl"},
        ).json()

        assert body["success"] is False
        assert body["error"] == "Simulated internal compiler crash"
        assert body["status"] == "INTERNAL_ERROR"
        assert "analysis_id" in body
        val = uuid.UUID(body["analysis_id"])
        assert val.version == 4

    def test_analyze_with_backend_error_returns_analysis_error(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """status must be ANALYSIS_ERROR when backend emits an ERROR diagnostic."""
        from app.analysis.models import AnalysisResult
        from app.backend.java.generator import BackendDiagnostic, BackendSeverity

        def mock_analyze_file(*args, **kwargs) -> AnalysisResult:
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[
                    BackendDiagnostic(
                        severity=BackendSeverity.ERROR,
                        message="simulated backend error",
                        code="BE_TEST",
                    )
                ],
                semantic_diagnostics=[],
                success=True,
                error=None,
                dependencies=[],
                ast=None,
                ir=None,
            )

        monkeypatch.setattr(
            "app.api.routers.analysis.AnalysisService.analyze_file", mock_analyze_file
        )

        ws_id = _create_workspace(workspace_root, {"syntax.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "syntax.cbl"},
        ).json()

        assert body["status"] == "ANALYSIS_ERROR"

    def test_analyze_with_backend_warning_returns_success(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """status must be SUCCESS when backend only emits a WARNING diagnostic."""
        from app.analysis.models import AnalysisResult
        from app.backend.java.generator import BackendDiagnostic, BackendSeverity

        def mock_analyze_file(*args, **kwargs) -> AnalysisResult:
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[
                    BackendDiagnostic(
                        severity=BackendSeverity.WARNING,
                        message="simulated backend warning",
                        code="BE_WARN",
                    )
                ],
                semantic_diagnostics=[],
                success=True,
                error=None,
                dependencies=[],
                ast=None,
                ir=None,
            )

        monkeypatch.setattr(
            "app.api.routers.analysis.AnalysisService.analyze_file", mock_analyze_file
        )

        ws_id = _create_workspace(workspace_root, {"syntax.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "syntax.cbl"},
        ).json()

        assert body["status"] == "SUCCESS"

    def test_analyze_with_semantic_error_returns_analysis_error_status(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """status must be ANALYSIS_ERROR when semantic errors are present."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})

        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()

        assert body["success"] is False
        assert body["status"] == "ANALYSIS_ERROR"


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
        body = response.json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")

    def test_analyze_missing_workspace_error_envelope(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """404 response must follow the canonical error envelope."""
        body = client.post(
            "/api/v1/workspaces/ghost-ws/analyze",
            json={"filename": "prog.cbl"},
        ).json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")

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
        body = response.json()
        _assert_error_envelope(body, expected_code="NOT_FOUND")

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
        body = response.json()
        _assert_error_envelope(body, expected_code="VALIDATION_ERROR")

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
        body = response.json()
        _assert_error_envelope(body, expected_code="VALIDATION_ERROR")

    def test_analyze_empty_filename_rejected(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """An empty filename must be rejected by request validation."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": ""},
        )
        assert response.status_code == 422
        body = response.json()
        _assert_error_envelope(body, expected_code="VALIDATION_ERROR")

    def test_analyze_whitespace_filename_rejected(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A whitespace-only filename must be rejected by request validation."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "   "},
        )
        assert response.status_code == 422
        body = response.json()
        _assert_error_envelope(body, expected_code="VALIDATION_ERROR")

    def test_analyze_dotdot_traversal_blocked(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """`../` traversal attempts must be rejected."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "../outside.cbl"},
        )
        assert response.status_code == 422
        body = response.json()
        _assert_error_envelope(body, expected_code="VALIDATION_ERROR")

    def test_analyze_double_dotdot_traversal_blocked(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """`../../` traversal attempts must be rejected."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "../../outside.cbl"},
        )
        assert response.status_code == 422
        body = response.json()
        _assert_error_envelope(body, expected_code="VALIDATION_ERROR")

    def test_analyze_absolute_path_blocked(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """An absolute path must not escape the workspace."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "/etc/passwd"},
        )
        assert response.status_code == 422
        body = response.json()
        _assert_error_envelope(body, expected_code="VALIDATION_ERROR")


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


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------


class TestAnalysisResponseSchema:
    """Tests for the AnalysisResponse schema."""

    def test_analyze_invalid_status_rejected(self) -> None:
        """Invalid status values cannot be accepted by the response model."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnalysisResponse(
                success=True,
                status="INVALID_STATUS_VALUE",
                analysis_id="uuid",
                workspace_id="uuid",
                filename="hello.cbl",
                source_metadata={
                    "extension": ".cbl",
                    "size_bytes": 100,
                    "sha256": "abc",
                },
                java_source="",
                ast=None,
                ir=None,
                diagnostics=[],
                error=None,
            )
