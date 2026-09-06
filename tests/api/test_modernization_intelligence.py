"""API tests for the Phase 4 modernization-intelligence endpoint (#112-#114)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.ingestion.workspace import WorkspaceManager
from app.main import app

client = TestClient(app)

_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ELIG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-AGE    PIC 9(3) VALUE 0.
       01 WS-RESULT PIC X(10) VALUE SPACE.
       PROCEDURE DIVISION.
       CHECK-AGE.
           IF WS-AGE >= 18
               MOVE 'ELIGIBLE' TO WS-RESULT
           ELSE
               MOVE 'DENIED' TO WS-RESULT
           END-IF.
           STOP RUN.
"""


def _mock_workspace(monkeypatch, tmp_path) -> None:
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)


def test_intelligence_endpoint_happy_path(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "elig.cbl").write_text(_SOURCE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence",
        json={"filename": "elig.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"business_rules", "risks", "strategies"}

    assert len(body["business_rules"]) == 2  # then + else
    rule = body["business_rules"][0]
    assert rule["rule_id"].startswith("BR-")
    assert rule["category"]
    assert rule["actions"][0]["kind"] == "ASSIGN"
    assert 0.0 <= rule["confidence"] <= 1.0

    assert any(s["is_primary"] for s in body["strategies"])
    assert sum(1 for s in body["strategies"] if s["is_primary"]) == 1


def test_intelligence_endpoint_is_deterministic(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "elig.cbl").write_text(_SOURCE, encoding="utf-8")
    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence"
    r1 = client.post(url, json={"filename": "elig.cbl"})
    r2 = client.post(url, json={"filename": "elig.cbl"})
    assert r1.json() == r2.json()


def test_intelligence_endpoint_path_traversal(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence",
        json={"filename": "../../../etc/passwd"},
    )
    assert resp.status_code == 403


def test_intelligence_endpoint_file_not_found(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence",
        json={"filename": "missing.cbl"},
    )
    assert resp.status_code == 404


def test_intelligence_endpoint_hides_internal_errors(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "elig.cbl").write_text(_SOURCE, encoding="utf-8")

    from app.analysis.service import AnalysisService

    def boom(self, path):
        raise ValueError("secret internal detail")

    monkeypatch.setattr(AnalysisService, "analyze_file", boom)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence",
        json={"filename": "elig.cbl"},
    )
    assert resp.status_code == 500
    assert "secret" not in resp.text
