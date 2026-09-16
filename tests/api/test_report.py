"""API tests for the Modernization Report endpoint (aggregates existing results)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.ingestion.workspace import WorkspaceManager
from app.main import app

client = TestClient(app)

_IF_ELSE = Path("tests/golden/if_else.cbl").read_text(encoding="utf-8")


def _mock_workspace(monkeypatch, tmp_path) -> None:
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)


def test_report_happy_path_aggregates_all_sections(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/report",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["analysis_success"] is True
    assert body["business_rules"]
    assert body["risks"] is not None
    assert body["coverage"] is not None
    assert body["confidence"] is not None
    assert body["architecture"] is not None
    assert body["project"] is not None
    assert body["compilation"]["success"] is True
    assert len(body["validation_stages"]) == 12
    assert body["unresolved_issues"]  # behavioral equivalence is INCONCLUSIVE here


def test_report_path_traversal_is_rejected(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/report",
        json={"filename": "../../etc/passwd"},
    )
    assert resp.status_code == 403


def test_report_missing_file_is_404(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/report",
        json={"filename": "missing.cbl"},
    )
    assert resp.status_code == 404


def test_report_is_deterministic(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/report"

    r1 = client.post(url, json={"filename": "if_else.cbl"})
    r2 = client.post(url, json={"filename": "if_else.cbl"})
    b1, b2 = r1.json(), r2.json()
    # compilation.workspace/duration_s/command/raw_output legitimately vary
    # per request (a fresh temp workspace dir + wall-clock timing each
    # time) -- everything that reflects the actual analysis must match.
    for body in (b1, b2):
        for volatile in ("workspace", "duration_s", "command", "raw_output"):
            body["compilation"].pop(volatile, None)
    assert b1 == b2


def test_report_never_claims_pass_overall_without_real_cobol(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/report",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    assert body["overall_status"] != "PASS"
    behavioral = next(
        s for s in body["validation_stages"] if s["stage"] == "Behavioral Equivalence"
    )
    assert behavioral["status"] == "INCONCLUSIVE"
    assert any("Behavioral Equivalence" in issue for issue in body["unresolved_issues"])


def test_report_reflects_architecture_unavailable_honestly(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    from app.java_modernization.errors import ArchitectureError

    def boom(bundle):
        raise ArchitectureError("no AST")

    monkeypatch.setattr("app.dataset.modernization_bundle.build_architecture", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/report",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    assert body["architecture"] is None
    assert "no AST" in body["architecture_reason"]
    assert body["project"] is None
    assert body["overall_status"] != "PASS"


def test_report_analysis_failure_hides_internal_errors(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    def boom(source_id, source, work_dir):
        raise ValueError("secret internal detail")

    monkeypatch.setattr("app.api.services.pipeline.build_analysis_bundle", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/report",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 500
    assert "secret" not in resp.text
