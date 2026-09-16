"""API tests for the Java Generation ("COBOL <-> Java") endpoint (#126/#127 over HTTP)."""

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


def test_java_generation_happy_path_returns_real_source_and_mappings(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    project = body["project"]
    assert project["files"]
    assert any(f.endswith(".java") for f in project["files"])

    # at least one artifact must carry a real COBOL source mapping
    mapped = [a for a in project["artifacts"] if a["source_locations"]]
    assert mapped
    for artifact in mapped:
        loc = artifact["source_locations"][0]
        assert loc["source_id"] == project["source_id"]
        assert loc["line_start"] is None or loc["line_start"] >= 1

    # generated Java actually compiled, per the real #127 compiler
    assert body["compilation"]["success"] is True


def test_java_generation_path_traversal_is_rejected(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java",
        json={"filename": "../secrets.cbl"},
    )
    assert resp.status_code == 403


def test_java_generation_missing_file_is_404(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java",
        json={"filename": "missing.cbl"},
    )
    assert resp.status_code == 404


def test_java_generation_is_deterministic(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java"

    r1 = client.post(url, json={"filename": "if_else.cbl"})
    r2 = client.post(url, json={"filename": "if_else.cbl"})

    assert r1.json()["project"]["files"] == r2.json()["project"]["files"]


def test_java_generation_unavailable_when_architecture_fails(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    from app.java_modernization.errors import ArchitectureError

    def boom(bundle):
        raise ArchitectureError("no AST")

    monkeypatch.setattr("app.dataset.modernization_bundle.build_architecture", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["project"] is None
    assert body["compilation"] is None
    assert "no AST" in body["reason"]


def test_java_generation_never_fabricates_java_on_generation_failure(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    from app.java_modernization.errors import GenerationError

    def boom(bundle, architecture):
        raise GenerationError("generation refused: no compilable output")

    monkeypatch.setattr("app.dataset.modernization_bundle.generate_project", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["project"] is None
    assert "generation refused" in body["reason"]


def test_java_generation_analysis_failure_hides_internal_errors(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    def boom(source_id, source, work_dir):
        raise ValueError("secret internal detail")

    monkeypatch.setattr("app.api.services.pipeline.build_analysis_bundle", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 500
    assert "secret" not in resp.text
