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

_COBOL_DIFFERENT_NAME = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. ACTUAL-PROG.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            CALL SOME-DEP
            STOP RUN.
"""

_COBOL_WITH_BUSINESS_RULES = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. RULE-TEST.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            IF A > B
                MOVE 1 TO X
            ELSE
                MOVE 2 TO Y
            END-IF.
            STOP RUN.
"""

_COBOL_COMBINED = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. COMBINED-PROG.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            CALL "OTHER-PROG"
            PERFORM SUB-PARA
            IF A > B
                MOVE 1 TO X
            ELSE
                MOVE 2 TO Y
            END-IF.
            STOP RUN.
        SUB-PARA.
            DISPLAY "SUB".
"""


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a module-scoped test client with AI mocked out."""
    from app.api.dependencies.ai import get_ai_orchestrator
    from app.ai.providers.fake import FakeLLMProvider
    from app.ai.orchestration.service import AIAnalysisOrchestrator
    from app.ai.explanation.service import CodeExplanationService
    from app.ai.documentation.service import DocumentationGenerationService

    def override_orchestrator():
        exp_provider = FakeLLMProvider(
            response_text="Summary:\nFake summary\n\nExplanation:\nFake explanation"
        )
        doc_provider = FakeLLMProvider(
            response_text="Title:\nFake doc\n\nOverview:\nFake overview\n\nSection:\nFake heading\nFake content"
        )
        return AIAnalysisOrchestrator(
            explanation_service=CodeExplanationService(exp_provider),
            documentation_service=DocumentationGenerationService(doc_provider),
        )

    app.dependency_overrides[get_ai_orchestrator] = override_orchestrator
    with TestClient(app) as tc:
        yield tc  # type: ignore[misc]
    app.dependency_overrides.pop(get_ai_orchestrator, None)


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


# ---------------------------------------------------------------------------
# Dependency Summary
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointDependenciesSummary:
    """Tests for the dependency analysis summary response."""

    def test_analyze_empty_dependency_summary(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A file with no dependencies must have an empty summary."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert "dependency_summary" in body
        summary = body["dependency_summary"]
        assert summary is not None
        assert summary["node_count"] == 1  # only the source file
        assert summary["edge_count"] == 0
        assert summary["resolved_target_count"] == 0
        assert summary["unresolved_target_count"] == 0
        assert summary["ambiguous_target_count"] == 0
        assert summary["dependency_counts"] == {}

    def test_analyze_fully_resolved_summary(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A file with dependencies present in the workspace must resolve fully."""
        ws_id = _create_workspace(
            workspace_root,
            {
                "perform_test.cbl": _COBOL_WITH_PERFORM,
                "calculate-bonus.cbl": _COBOL_HELLO,
            },
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "perform_test.cbl"},
        ).json()
        summary = body["dependency_summary"]
        assert summary is not None
        assert summary["node_count"] == 2
        assert summary["edge_count"] == 1
        assert summary["resolved_target_count"] == 1
        assert summary["unresolved_target_count"] == 0
        assert summary["ambiguous_target_count"] == 0
        assert summary["dependency_counts"] == {"PERFORM": 1}

    def test_analyze_mixed_resolution_summary(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A file with some missing dependencies must show mixed resolution."""
        ws_id = _create_workspace(
            workspace_root,
            {
                "multi.cbl": _COBOL_WITH_MULTIPLE_DEPS,
                "subprog.cbl": _COBOL_HELLO,
            },
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "multi.cbl"},
        ).json()
        summary = body["dependency_summary"]
        assert summary is not None
        assert summary["node_count"] == 3
        assert summary["edge_count"] == 2
        assert summary["resolved_target_count"] == 1  # subprog
        assert summary["unresolved_target_count"] == 1  # init-rtn
        assert summary["ambiguous_target_count"] == 0
        assert summary["dependency_counts"] == {"CALL": 1, "PERFORM": 1}

    def test_analyze_dependency_types_serialization(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Dependency types must be correctly serialized as string keys."""
        ws_id = _create_workspace(
            workspace_root,
            {"dup.cbl": _COBOL_WITH_DUPLICATES},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "dup.cbl"},
        ).json()
        summary = body["dependency_summary"]
        assert summary is not None
        counts = summary["dependency_counts"]
        assert "CALL" in counts
        assert "PERFORM" in counts
        assert isinstance(counts["CALL"], int)
        assert isinstance(counts["PERFORM"], int)

    def test_analyze_canonical_identifier(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The dependency graph root must use the PROGRAM-ID, not the filename."""
        from app.analysis.dependencies.graph import DependencyGraph

        original_from_dependencies = DependencyGraph.from_dependencies
        captured_source = None

        def mock_from_dependencies(source: str, dependencies: list) -> DependencyGraph:
            nonlocal captured_source
            captured_source = source
            return original_from_dependencies(source, dependencies)

        monkeypatch.setattr(
            "app.api.routers.analysis.DependencyGraph.from_dependencies",
            mock_from_dependencies,
        )

        ws_id = _create_workspace(
            workspace_root,
            {"some_file.cbl": _COBOL_DIFFERENT_NAME},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "some_file.cbl"},
        ).json()

        assert body["success"] is True
        assert body["dependency_summary"] is not None
        assert captured_source == "ACTUAL-PROG"

    def test_analyze_semantic_error_preserves_dependency_summary(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A semantic analysis error may still expose dependency summary when the AST is available."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()
        assert body["success"] is False
        assert "dependency_summary" in body
        assert body["dependency_summary"] is not None

    def test_analyze_internal_error_has_no_summary(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An internal error where no AST is generated must yield no dependency summary."""
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

        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()

        assert body["success"] is False
        assert body["error"] == "Simulated internal compiler crash"
        assert body["status"] == "INTERNAL_ERROR"
        assert body["dependency_summary"] is None

    def test_analyze_dependency_graph_empty(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A program with no dependencies must yield an empty graph."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        graph = body["dependency_graph"]
        assert graph is not None
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["identifier"] == "HELLO-WORLD"
        assert len(graph["edges"]) == 0

    def test_analyze_dependency_graph_call(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A program with a CALL dependency must yield a graph with a CALL edge."""
        ws_id = _create_workspace(
            workspace_root,
            {"call_test.cbl": _COBOL_WITH_CALL, "CUSTOMER-SERVICE": _COBOL_HELLO},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "call_test.cbl"},
        ).json()
        graph = body["dependency_graph"]
        assert graph is not None
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1
        edge = graph["edges"][0]
        assert edge["source"] == "CALL-TEST"
        assert edge["target"] == '"CUSTOMER-SERVICE"'
        assert edge["dependency_type"] == "CALL"

    def test_analyze_dependency_graph_perform(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A program with a PERFORM dependency must yield a graph with a PERFORM edge."""
        ws_id = _create_workspace(
            workspace_root,
            {"perform_test.cbl": _COBOL_WITH_PERFORM},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "perform_test.cbl"},
        ).json()
        graph = body["dependency_graph"]
        assert graph is not None
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1
        edge = graph["edges"][0]
        assert edge["source"] == "PERFORM-TEST"
        assert edge["target"] == "CALCULATE-BONUS"
        assert edge["dependency_type"] == "PERFORM"

    def test_analyze_dependency_graph_duplicates(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A program with multiple CALL and PERFORM to same targets deduplicates edges."""
        ws_id = _create_workspace(
            workspace_root,
            {"dup.cbl": _COBOL_WITH_DUPLICATES},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "dup.cbl"},
        ).json()
        graph = body["dependency_graph"]
        assert graph is not None
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 2

        edges = graph["edges"]
        assert edges[0]["target"] == "BONUSMOD"
        assert edges[0]["dependency_type"] == "CALL"

        assert edges[1]["target"] == "WORK"
        assert edges[1]["dependency_type"] == "PERFORM"

    def test_analyze_dependency_graph_source_location(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """The dependency graph edge must preserve the source location."""
        ws_id = _create_workspace(
            workspace_root,
            {"call_test.cbl": _COBOL_WITH_CALL},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "call_test.cbl"},
        ).json()
        edge = body["dependency_graph"]["edges"][0]
        loc = edge["source_location"]
        assert loc is not None
        assert loc["type"] == "Position"
        assert isinstance(loc["line"], int)
        assert isinstance(loc["column"], int)
        assert isinstance(loc["offset"], int)
        assert loc["filename"].endswith("call_test.cbl")

    def test_analyze_dependency_graph_semantic_error(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A semantic analysis error may still expose dependency graph when the AST is available."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl"},
        ).json()
        assert body["success"] is False
        assert body["dependency_graph"] is not None
        assert len(body["dependency_graph"]["nodes"]) == 1

    def test_analyze_dependency_graph_internal_error(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An internal error where no AST is generated must yield no dependency graph."""
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

        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()

        assert body["success"] is False
        assert body["dependency_graph"] is None

    def test_analyze_dependency_graph_nodes_identifiers(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Graph nodes must contain correct canonical root and target identifiers."""
        ws_id = _create_workspace(
            workspace_root,
            {"call_test.cbl": _COBOL_WITH_CALL, "CUSTOMER-SERVICE": _COBOL_HELLO},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "call_test.cbl"},
        ).json()
        graph = body["dependency_graph"]
        assert graph is not None
        node_ids = {node["identifier"] for node in graph["nodes"]}
        assert "CALL-TEST" in node_ids
        assert '"CUSTOMER-SERVICE"' in node_ids

    def test_analyze_dependency_graph_summary_match(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """The dependency graph and summary metrics must exactly align."""
        ws_id = _create_workspace(
            workspace_root,
            {"dup.cbl": _COBOL_WITH_DUPLICATES},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "dup.cbl"},
        ).json()
        graph = body["dependency_graph"]
        summary = body["dependency_summary"]

        assert summary["node_count"] == len(graph["nodes"])
        assert summary["edge_count"] == len(graph["edges"])

    def test_analyze_dependency_graph_json_types(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Enum values must serialize to raw JSON strings without leaking domain objects."""
        ws_id = _create_workspace(
            workspace_root,
            {"dup.cbl": _COBOL_WITH_DUPLICATES},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "dup.cbl"},
        )
        body = response.json()
        graph = body["dependency_graph"]

        edge_types = {edge["dependency_type"] for edge in graph["edges"]}
        assert edge_types == {"CALL", "PERFORM"}
        # Verify JSON serialization does not contain Python Enum string representations
        raw_json = response.text
        assert "DependencyType.CALL" not in raw_json
        assert "DependencyType.PERFORM" not in raw_json

    def test_analyze_dependency_graph_backward_compatibility(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Verify existing AnalysisResponse fields remain intact alongside the graph."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()

        expected_fields = {
            "success",
            "status",
            "analysis_id",
            "workspace_id",
            "filename",
            "source_metadata",
            "java_source",
            "ast",
            "ir",
            "diagnostics",
            "dependencies",
            "dependency_summary",
            "dependency_graph",
            "error",
        }
        actual_fields = set(body.keys())
        assert expected_fields.issubset(actual_fields)

    def test_analyze_dependency_graph_determinism(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Repeated equivalent analysis must produce stable node and edge ordering."""
        ws_id = _create_workspace(
            workspace_root,
            {"dup.cbl": _COBOL_WITH_DUPLICATES},
        )

        body1 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "dup.cbl"},
        ).json()

        body2 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "dup.cbl"},
        ).json()

        graph1 = body1["dependency_graph"]
        graph2 = body2["dependency_graph"]

        assert graph1["nodes"] == graph2["nodes"]
        assert graph1["edges"] == graph2["edges"]


class TestAnalyzeBusinessRules:
    """Tests for the business_rules extraction integration in the analysis API."""

    def test_analyze_business_rules_nominal(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Verify business rules are extracted and returned for valid source."""
        ws_id = _create_workspace(
            workspace_root,
            {"rules.cbl": _COBOL_WITH_BUSINESS_RULES},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "rules.cbl"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

        rules = body.get("business_rules")
        assert rules is not None
        assert len(rules) == 2

        # Verify normalization and literals preservation
        assert rules[0]["condition"] == "A > B"
        assert rules[0]["actions"] == ["MOVE 1 TO X"]

        assert rules[1]["condition"] == "NOT ( A > B )"
        assert rules[1]["actions"] == ["MOVE 2 TO Y"]

    def test_analyze_business_rules_empty(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Verify empty rules result is returned when no rules are present."""
        ws_id = _create_workspace(
            workspace_root,
            {"hello.cbl": _COBOL_HELLO},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

        rules = body.get("business_rules")
        assert rules is not None
        assert len(rules) == 0

    def test_analyze_business_rules_semantic_error(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Verify rules are returned even if semantic errors exist, provided AST is valid."""
        ws_id = _create_workspace(
            workspace_root,
            {"undef.cbl": _COBOL_UNDEFINED},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undef.cbl"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["status"] == "ANALYSIS_ERROR"

        # AST is constructed despite undefined variables
        assert body["business_rules"] is not None

    def test_analyze_business_rules_internal_error(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify rules are null if analysis fails before AST creation."""
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

        ws_id = _create_workspace(
            workspace_root,
            {"hello.cbl": _COBOL_HELLO},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["status"] == "INTERNAL_ERROR"

        # No AST, so no rules could be extracted
        assert body.get("business_rules") is None


class TestPhase1IntelligenceIntegration:
    """Tests to prove dependency and business rule intelligence coexist."""

    def test_analyze_dependency_only(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """REQUIRED TEST 1: Source with dependencies but no business rules."""
        ws_id = _create_workspace(
            workspace_root,
            {"call_test.cbl": _COBOL_WITH_CALL, "CUSTOMER-SERVICE": _COBOL_HELLO},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "call_test.cbl"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

        # Dependency graph is correct
        graph = body["dependency_graph"]
        assert graph is not None
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1

        # Dependency summary is correct
        summary = body["dependency_summary"]
        assert summary is not None
        assert summary["node_count"] == 2
        assert summary["edge_count"] == 1

        # Business rules follows empty-result convention
        rules = body.get("business_rules")
        assert rules is not None
        assert rules == []

    def test_analyze_business_rule_only(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """REQUIRED TEST 2: Source with business rules but no dependencies."""
        ws_id = _create_workspace(
            workspace_root,
            {"rules.cbl": _COBOL_WITH_BUSINESS_RULES},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "rules.cbl"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

        # Business rules are returned
        rules = body.get("business_rules")
        assert rules is not None
        assert len(rules) == 2

        # Rules are normalized
        assert rules[0]["condition"] == "A > B"
        assert rules[1]["condition"] == "NOT ( A > B )"

        # Dependency intelligence follows empty/no-dependency convention
        graph = body["dependency_graph"]
        assert graph is not None
        assert len(graph["nodes"]) == 1  # Root node
        assert len(graph["edges"]) == 0

        summary = body["dependency_summary"]
        assert summary is not None
        assert summary["node_count"] == 1
        assert summary["edge_count"] == 0

    def test_analyze_combined(self, client: TestClient, workspace_root: Path) -> None:
        """REQUIRED TEST 3: Source with both dependencies and business rules."""
        ws_id = _create_workspace(
            workspace_root,
            {"combined.cbl": _COBOL_COMBINED},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

        # Both capabilities must be present
        assert body["dependency_graph"] is not None
        assert body["dependency_summary"] is not None
        assert body["business_rules"] is not None
        graph = body["dependency_graph"]
        rules = body["business_rules"]

        # Verify dependency graph
        assert len(graph["nodes"]) == 3  # COMBINED-PROG, "OTHER-PROG", SUB-PARA
        assert len(graph["edges"]) == 2  # CALL, PERFORM

        # Verify business rules
        assert len(rules) == 2
        assert rules[0]["condition"] == "A > B"
        assert rules[0]["actions"] == ["MOVE 1 TO X"]
        assert rules[1]["condition"] == "NOT ( A > B )"
        assert rules[1]["actions"] == ["MOVE 2 TO Y"]

    def test_graph_summary_consistency(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Verify summary counts match graph elements exactly."""
        ws_id = _create_workspace(
            workspace_root,
            {"combined.cbl": _COBOL_COMBINED},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        ).json()

        graph = body["dependency_graph"]
        summary = body["dependency_summary"]

        assert summary["node_count"] == len(graph["nodes"])
        assert summary["edge_count"] == len(graph["edges"])

    def test_business_rule_normalization(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Verify the API exposes the already-normalized BusinessRule."""
        ws_id = _create_workspace(
            workspace_root,
            {"combined.cbl": _COBOL_COMBINED},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        ).json()

        rules = body.get("business_rules")
        assert rules is not None
        assert len(rules) == 2
        assert rules[0]["condition"] == "A > B"
        assert rules[1]["condition"] == "NOT ( A > B )"

    def test_empty_analysis(self, client: TestClient, workspace_root: Path) -> None:
        """Test a valid program containing neither dependencies nor business rules."""
        ws_id = _create_workspace(
            workspace_root,
            {"hello.cbl": _COBOL_HELLO},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["success"] is True

        graph = body["dependency_graph"]
        assert len(graph["nodes"]) == 1
        assert len(graph["edges"]) == 0

        summary = body["dependency_summary"]
        assert summary["node_count"] == 1
        assert summary["edge_count"] == 0

        rules = body.get("business_rules")
        assert rules is not None
        assert len(rules) == 0

    def test_semantic_error(self, client: TestClient, workspace_root: Path) -> None:
        """Test that intelligence results are retained when AST is constructed despite errors."""
        ws_id = _create_workspace(
            workspace_root,
            {"undef.cbl": _COBOL_UNDEFINED},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undef.cbl"},
        ).json()

        assert body["success"] is False
        assert body["status"] == "ANALYSIS_ERROR"

        # Verify diagnostics
        assert len(body["diagnostics"]) > 0

        # Available intelligence remains available
        assert body["dependency_summary"] is not None
        assert body["dependency_graph"] is not None
        assert body["business_rules"] is not None

    def test_internal_error(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When AST creation fails, verify unavailable conventions are followed."""
        from app.analysis.models import AnalysisResult

        def mock_analyze_file(*args, **kwargs) -> AnalysisResult:
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=False,
                error=Exception("Internal error"),
                dependencies=[],
                ast=None,
                ir=None,
            )

        monkeypatch.setattr(
            "app.api.routers.analysis.AnalysisService.analyze_file", mock_analyze_file
        )

        ws_id = _create_workspace(
            workspace_root,
            {"hello.cbl": _COBOL_HELLO},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()

        assert body["success"] is False
        assert body["status"] == "INTERNAL_ERROR"

        # Dependency graph follows unavailable convention
        assert body.get("dependency_graph") is None
        # Dependency summary follows unavailable convention
        assert body.get("dependency_summary") is None
        # Business rules follows unavailable convention
        assert body.get("business_rules") is None

    def test_json_serialization(self, client: TestClient, workspace_root: Path) -> None:
        """Verify the complete response can be serialized to JSON with correct types."""
        ws_id = _create_workspace(
            workspace_root,
            {"combined.cbl": _COBOL_COMBINED},
        )
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        )
        assert response.status_code == 200

        # It's already JSON serialized by the client, let's verify types
        body = response.json()

        graph = body["dependency_graph"]
        assert isinstance(graph["nodes"], list)
        assert isinstance(graph["edges"], list)
        for edge in graph["edges"]:
            assert isinstance(edge["dependency_type"], str)

        rules = body["business_rules"]
        assert isinstance(rules, list)
        for rule in rules:
            assert isinstance(rule["condition"], str)
            assert isinstance(rule["actions"], list)
            assert all(isinstance(a, str) for a in rule["actions"])
            if rule.get("source_location"):
                loc = rule["source_location"]
                assert isinstance(loc, dict)
                assert "line" in loc
                assert "column" in loc
                assert "filename" in loc

    def test_backward_compatibility(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Verify existing fields remain available."""
        ws_id = _create_workspace(
            workspace_root,
            {"combined.cbl": _COBOL_COMBINED},
        )
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        ).json()

        expected_fields = {
            "success",
            "status",
            "ast",
            "ir",
            "diagnostics",
            "dependencies",
            "dependency_summary",
            "dependency_graph",
            "business_rules",
            "error",
        }
        actual_fields = set(body.keys())
        assert expected_fields.issubset(actual_fields)

    def test_determinism(self, client: TestClient, workspace_root: Path) -> None:
        """Verify deterministic ordering of nodes, edges, rules, and actions."""
        ws_id = _create_workspace(
            workspace_root,
            {"combined.cbl": _COBOL_COMBINED},
        )

        body1 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        ).json()

        body2 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        ).json()

        assert body1["dependency_graph"]["nodes"] == body2["dependency_graph"]["nodes"]
        assert body1["dependency_graph"]["edges"] == body2["dependency_graph"]["edges"]

        assert body1["business_rules"] == body2["business_rules"]

        for rule1, rule2 in zip(body1["business_rules"], body2["business_rules"]):
            assert rule1["actions"] == rule2["actions"]


# ---------------------------------------------------------------------------
# AI Analysis Orchestration
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointAIOrchestration:
    """Tests for AI capabilities orchestration during analysis."""

    def test_analyze_omits_ai_when_not_requested(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """ai_analysis must be None if ai_capabilities are not requested. Existing fields must be present."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl"},
        ).json()
        assert body["success"] is True
        assert body.get("ai_analysis") is None

        # Verify backward compatibility for existing fields
        assert "status" in body
        assert "ast" in body
        assert "dependencies" in body
        assert "dependency_summary" in body
        assert "dependency_graph" in body
        assert "business_rules" in body
        assert "diagnostics" in body
        assert "error" in body
        assert "source_metadata" in body

    def test_analyze_with_explanation_capability(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Requesting EXPLANATION must return a populated CodeExplanationResponse."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl", "ai_capabilities": ["EXPLANATION"]},
        ).json()
        assert body["success"] is True
        ai = body["ai_analysis"]
        assert ai is not None
        assert ai["explanation"] is not None
        assert ai["explanation"]["summary"] == "Fake summary"
        assert ai["explanation"]["explanation"] == "Fake explanation"
        assert ai["documentation"] is None

    def test_analyze_with_documentation_capability(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Requesting DOCUMENTATION must return a populated DocumentationResponse."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl", "ai_capabilities": ["DOCUMENTATION"]},
        ).json()
        assert body["success"] is True
        ai = body["ai_analysis"]
        assert ai is not None
        assert ai["documentation"] is not None
        assert ai["documentation"]["title"] == "Fake doc"
        assert ai["documentation"]["overview"] == "Fake overview"
        assert len(ai["documentation"]["sections"]) == 1
        assert ai["documentation"]["sections"][0]["heading"] == "Fake heading"
        assert ai["documentation"]["sections"][0]["content"] == "Fake content"
        assert ai["explanation"] is None

    def test_analyze_with_combined_capabilities(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Requesting both EXPLANATION and DOCUMENTATION returns both responses."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={
                "filename": "hello.cbl",
                "ai_capabilities": ["EXPLANATION", "DOCUMENTATION"],
            },
        ).json()
        assert body["success"] is True
        ai = body["ai_analysis"]
        assert ai is not None
        assert ai["explanation"] is not None
        assert ai["documentation"] is not None

    def test_analyze_ai_fails_gracefully(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AI provider failure should not fail the whole request, but update status."""
        from app.ai.providers.errors import LLMProviderUnavailableError

        def mock_analyze(*args, **kwargs):
            raise LLMProviderUnavailableError("Fake timeout")

        monkeypatch.setattr(
            "app.ai.orchestration.service.AIAnalysisOrchestrator.analyze", mock_analyze
        )

        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "hello.cbl", "ai_capabilities": ["EXPLANATION"]},
        ).json()

        # It preserves the analysis result but updates the error and status
        assert body["success"] is True  # Phase-1 succeeded
        assert body["status"] == "INTERNAL_ERROR"
        assert body["ai_analysis"] is None
        assert "Fake timeout" in body["error"]
        # Make sure phase 1 data remains intact
        assert body["ast"] is not None
        assert body["java_source"] != ""

    def test_analyze_skips_ai_on_phase1_failure(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """If semantic analysis fails, AI shouldn't be executed even if requested."""
        ws_id = _create_workspace(workspace_root, {"undefined.cbl": _COBOL_UNDEFINED})
        body = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "undefined.cbl", "ai_capabilities": ["EXPLANATION"]},
        ).json()
        assert body["success"] is False
        assert body.get("ai_analysis") is None

    def test_analyze_preserves_dependency_and_business_rules(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Using AI should not alter Phase-1 results like dependencies and business rules."""
        ws_id = _create_workspace(workspace_root, {"combined.cbl": _COBOL_COMBINED})

        # Run without AI
        body_no_ai = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl"},
        ).json()

        # Run with AI
        body_with_ai = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl", "ai_capabilities": ["EXPLANATION"]},
        ).json()

        assert body_no_ai["dependency_graph"] == body_with_ai["dependency_graph"]
        assert body_no_ai["business_rules"] == body_with_ai["business_rules"]
        assert body_no_ai["diagnostics"] == body_with_ai["diagnostics"]

    def test_ai_response_is_json_safe(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """The AI response structures must be fully JSON-serializable."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})
        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={
                "filename": "hello.cbl",
                "ai_capabilities": ["EXPLANATION", "DOCUMENTATION"],
            },
        )
        body = response.json()
        json_str = json.dumps(body)
        assert isinstance(json_str, str)
        _assert_json_safe(body)

    def test_analyze_propagates_phase1_context(
        self, client: TestClient, workspace_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The orchestrator must receive the Phase-1 analysis context."""
        ws_id = _create_workspace(workspace_root, {"combined.cbl": _COBOL_COMBINED})

        captured_context = {}

        from app.ai.orchestration.service import AIAnalysisOrchestrator

        original_analyze = AIAnalysisOrchestrator.analyze

        def mock_analyze(
            self_inst, source: str, capabilities: set, context: dict | None = None
        ):
            captured_context.update(context or {})
            return original_analyze(self_inst, source, capabilities, context)

        monkeypatch.setattr(
            "app.ai.orchestration.service.AIAnalysisOrchestrator.analyze", mock_analyze
        )

        response = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={"filename": "combined.cbl", "ai_capabilities": ["EXPLANATION"]},
        ).json()

        assert response.get("success") is True, f"Response failed: {response}"

        assert captured_context["correlation_id"] == response["analysis_id"]
        assert len(captured_context["dependencies"]) == len(response["dependencies"])
        assert (
            captured_context["dependency_summary"].node_count
            == response["dependency_summary"]["node_count"]
        )
        assert len(captured_context["dependency_graph"].edges) == len(
            response["dependency_graph"]["edges"]
        )
        assert len(captured_context["business_rules"]) == len(
            response["business_rules"]
        )

        assert len(captured_context["diagnostics"]) == len(
            response.get("diagnostics", [])
        )
        assert captured_context["source_metadata"] is not None
        assert len(captured_context["dependencies"]) > 0
        assert len(captured_context["business_rules"]) > 0

    def test_analyze_determinism(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Two requests for the same source must produce the same AI artifacts."""
        ws_id = _create_workspace(workspace_root, {"hello.cbl": _COBOL_HELLO})

        body1 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={
                "filename": "hello.cbl",
                "ai_capabilities": ["EXPLANATION", "DOCUMENTATION"],
            },
        ).json()

        body2 = client.post(
            f"/api/v1/workspaces/{ws_id}/analyze",
            json={
                "filename": "hello.cbl",
                "ai_capabilities": ["EXPLANATION", "DOCUMENTATION"],
            },
        ).json()

        # The AI artifacts should be completely identical for the fake provider
        assert body1["ai_analysis"] == body2["ai_analysis"]
