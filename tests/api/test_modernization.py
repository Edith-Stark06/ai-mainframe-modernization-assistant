import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.ingestion.workspace import WorkspaceManager

client = TestClient(app)


def test_modernization_pipeline_not_found(monkeypatch) -> None:
    # Test file not found error
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path="/non/existent/path")

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)

    ws_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/modernization/pipeline",
        json={"filename": "unknown.cbl"},
    )

    assert resp.status_code == 404
    assert "Source file not found" in resp.text
