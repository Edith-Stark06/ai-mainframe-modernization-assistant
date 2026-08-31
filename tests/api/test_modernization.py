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


def test_modernization_pipeline_path_traversal(monkeypatch, tmp_path) -> None:
    # Test path traversal prevention
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)

    ws_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/modernization/pipeline",
        json={"filename": "../../../etc/passwd"},
    )

    assert resp.status_code == 403
    assert "Forbidden path traversal detected" in resp.text


def test_modernization_pipeline_hides_exceptions(monkeypatch, tmp_path) -> None:
    # Test internal exception hiding
    (tmp_path / "valid.cbl").touch()

    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    def mock_analyze(self, path):
        raise ValueError("Sensitive internal secret path information")

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)
    from app.analysis.service import AnalysisService

    monkeypatch.setattr(AnalysisService, "analyze_file", mock_analyze)

    ws_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/modernization/pipeline",
        json={"filename": "valid.cbl"},
    )

    assert resp.status_code == 500
    assert "Analysis failed" in resp.text
    assert "Sensitive" not in resp.text
