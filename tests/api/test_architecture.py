"""API tests for the Architecture endpoint (#125 over HTTP)."""

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


def test_architecture_happy_path_returns_real_components(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["reason"] is None
    arch = body["architecture"]
    assert arch is not None
    assert arch["source_id"]
    # every component must carry real source provenance -- never invented
    for component in arch["components"]:
        assert component["component_id"]
        assert component["type"] in {
            "SERVICE",
            "DOMAIN",
            "REPOSITORY",
            "DTO",
            "CONFIGURATION",
            "INTEGRATION",
        }


def test_architecture_path_traversal_is_rejected(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture",
        json={"filename": "../../../etc/passwd"},
    )
    assert resp.status_code == 403


def test_architecture_missing_file_is_404(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture",
        json={"filename": "missing.cbl"},
    )
    assert resp.status_code == 404


def test_architecture_response_is_deterministic(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture"

    r1 = client.post(url, json={"filename": "if_else.cbl"})
    r2 = client.post(url, json={"filename": "if_else.cbl"})

    b1, b2 = r1.json()["architecture"], r2.json()["architecture"]
    assert b1["architecture_id"] == b2["architecture_id"]
    assert b1["components"] == b2["components"]
    assert b1 == b2


def test_architecture_preserves_source_provenance(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )
    arch = resp.json()["architecture"]
    assert arch["source_mappings"]
    for refs in arch["source_mappings"].values():
        for ref in refs:
            assert ref["source_id"] == arch["source_id"]


def test_architecture_unavailable_when_no_ast_is_returned_honestly(
    monkeypatch, tmp_path
):
    """A structural analysis failure must produce available=False + a
    reason, never a fabricated architecture."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    from app.java_modernization.errors import ArchitectureError

    def boom(bundle):
        raise ArchitectureError(f"{bundle.source_id}: no AST")

    monkeypatch.setattr("app.dataset.modernization_bundle.build_architecture", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["architecture"] is None
    assert "no AST" in body["reason"]


def test_architecture_analysis_failure_hides_internal_errors(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    def boom(source_id, source, work_dir):
        raise ValueError("secret internal detail")

    monkeypatch.setattr("app.api.services.pipeline.build_analysis_bundle", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 500
    assert "secret" not in resp.text
