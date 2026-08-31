import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.rag.orchestration.models import RAGResult, RAGRequest, RetrievedContext
from app.api.routers.chat import get_rag_orchestrator

client = TestClient(app)


class MockRAGOrchestrator:
    def orchestrate(self, request: RAGRequest) -> RAGResult:
        if request.query == "rag_fail":
            raise RuntimeError("Test RAG Failure")

        context = RetrievedContext(results=tuple())
        return RAGResult(
            request=request,
            context=context,
            ai_error="AI failed" if "ai_fail" in request.query else None,
        )


def override_get_rag():
    return MockRAGOrchestrator()


app.dependency_overrides[get_rag_orchestrator] = override_get_rag


def test_chat_endpoint_success():
    resp = client.post(
        "/api/v1/chat/", json={"query": "hello", "workspace_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "hello"
    assert data["error"] is None


def test_chat_endpoint_rag_fail():
    resp = client.post(
        "/api/v1/chat/", json={"query": "rag_fail", "workspace_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "RAG Orchestration failed" in data["error"]


def test_chat_endpoint_ai_fail():
    resp = client.post(
        "/api/v1/chat/", json={"query": "ai_fail", "workspace_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] == "AI failed"
