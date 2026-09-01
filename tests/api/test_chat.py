import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.rag.orchestration.models import RAGResult, RAGRequest, RetrievedContext
from app.api.routers.chat import (
    get_rag_orchestrator,
    get_workspace_manager,
    get_analysis_service,
)
from app.ai.orchestration.models import AIAnalysisResult

client = TestClient(app)


class MockRAGOrchestrator:
    def orchestrate(self, request: RAGRequest) -> RAGResult:
        assert "workspace_id" in request.filters, "workspace_id filter must be set"

        if request.query == "rag_fail":
            raise RuntimeError("Secret RAG Failure")

        context = RetrievedContext(results=tuple())

        if "ai_fail" in request.query:
            return RAGResult(
                request=request,
                context=context,
                ai_error="Secret AI failed",
            )
        elif "explain" in request.query:

            class MockExpl:
                def __str__(self):
                    return "This is an explanation"

            return RAGResult(
                request=request,
                context=context,
                ai_result=AIAnalysisResult(explanation=MockExpl()),  # type: ignore
            )

        return RAGResult(
            request=request,
            context=context,
            ai_error=None,
        )


def override_get_rag():
    return MockRAGOrchestrator()


@pytest.fixture(autouse=True)
def _mock_rag_orchestrator():
    """
    Scope the get_rag_orchestrator override to this file's tests only.

    Regression: this was previously a bare module-level assignment
    (app.dependency_overrides[get_rag_orchestrator] = override_get_rag) with
    no teardown. Since pytest imports every test module during collection
    before running any test, that line executed as soon as this file was
    collected -- permanently overriding get_rag_orchestrator for the rest of
    the pytest process, regardless of test/file order. Any other test in the
    suite that expected the *real* get_rag_orchestrator dependency (e.g. a
    genuine end-to-end integration test) would silently get this mock
    instead, with no error -- just wrong results.
    """
    app.dependency_overrides[get_rag_orchestrator] = override_get_rag
    yield
    app.dependency_overrides.pop(get_rag_orchestrator, None)


def test_chat_endpoint_validation():
    # Empty query should fail
    resp = client.post(
        "/api/v1/chat/", json={"query": "", "workspace_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 422

    # Whitespace-only query should fail
    resp = client.post(
        "/api/v1/chat/", json={"query": "   ", "workspace_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 422

    # Invalid UUID should fail
    resp = client.post(
        "/api/v1/chat/", json={"query": "q", "workspace_id": "invalid-uuid"}
    )
    assert resp.status_code == 422

    # top_k > 100 should fail
    resp = client.post(
        "/api/v1/chat/",
        json={"query": "q", "workspace_id": str(uuid.uuid4()), "top_k": 200},
    )
    assert resp.status_code == 422


def test_chat_endpoint_success():
    resp = client.post(
        "/api/v1/chat/", json={"query": "hello", "workspace_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "hello"
    assert data["error"] is None


def test_chat_endpoint_ai_success():
    resp = client.post(
        "/api/v1/chat/",
        json={
            "query": "explain this",
            "workspace_id": str(uuid.uuid4()),
            "ai_capabilities": ["EXPLANATION"],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "This is an explanation"


def test_chat_endpoint_rag_fail():
    resp = client.post(
        "/api/v1/chat/", json={"query": "rag_fail", "workspace_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "internal error" in data["error"]
    assert "Secret" not in data["error"]


def test_chat_endpoint_ai_fail():
    resp = client.post(
        "/api/v1/chat/", json={"query": "ai_fail", "workspace_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "internal error" in data["error"]
    assert "Secret" not in data["error"]


def test_chat_endpoint_modernization_context(monkeypatch, tmp_path):
    (tmp_path / "valid.cbl").touch()

    class MockWSManager:
        def get(self, ws_id):
            if ws_id == "00000000-0000-0000-0000-000000000000":
                raise KeyError("Workspace not found")
            from app.ingestion.models import WorkspaceRecord

            return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    class MockAnalysisService:
        def analyze_file(self, path):
            from app.analysis.models import AnalysisResult

            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=True,
                dependencies=[],
                error=None,
                ast=None,
                ir=None,
            )

    app.dependency_overrides[get_workspace_manager] = lambda: MockWSManager()
    app.dependency_overrides[get_analysis_service] = lambda: MockAnalysisService()

    valid_uuid = str(uuid.uuid4())

    resp = client.post(
        "/api/v1/chat/",
        json={
            "query": "explain this program",
            "workspace_id": valid_uuid,
            "include_modernization_context": True,
            "filename": "valid.cbl",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["modernization_data"] is not None
    assert "flow" in data["modernization_data"]

    # modernization_data being attached to the response is not sufficient on
    # its own -- the AI generation step must actually succeed and its answer
    # must reach the response (this exercises chat.py's real answer-extraction
    # logic against MockRAGOrchestrator's populated-explanation branch; the
    # deeper "does modernization context actually reach the real AI prompt
    # without crashing" case is covered end-to-end, with the real
    # AIAnalysisOrchestrator, by
    # tests/rag/test_orchestration.py::test_orchestration_modernization_context_reaches_generated_prompt).
    assert data["error"] is None
    assert data["answer"] != ""

    # Missing filename should raise 400
    resp_missing = client.post(
        "/api/v1/chat/",
        json={
            "query": "hello",
            "workspace_id": valid_uuid,
            "include_modernization_context": True,
        },
    )
    assert resp_missing.status_code == 400

    # Missing file should raise 404
    resp_not_found = client.post(
        "/api/v1/chat/",
        json={
            "query": "hello",
            "workspace_id": valid_uuid,
            "include_modernization_context": True,
            "filename": "missing.cbl",
        },
    )
    assert resp_not_found.status_code == 404

    # Path traversal should raise 403
    resp_traversal = client.post(
        "/api/v1/chat/",
        json={
            "query": "hello",
            "workspace_id": valid_uuid,
            "include_modernization_context": True,
            "filename": "../secrets.txt",
        },
    )
    assert resp_traversal.status_code == 403

    app.dependency_overrides.pop(get_workspace_manager, None)
    app.dependency_overrides.pop(get_analysis_service, None)
