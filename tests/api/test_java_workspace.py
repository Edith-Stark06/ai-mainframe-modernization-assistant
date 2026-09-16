"""
API tests for the Java Workspace endpoint.

Covers real generated Java/compilation/behavioral status (reusing the
same pipeline as PR #122's /java and /validation), the real
deterministic candidate identity, and -- centrally -- that quality-loop
execution state (iterations, repair history, human review, audit
trail) is honestly empty/NOT_AVAILABLE in this environment (no LLM
provider configured), never fabricated.
"""

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


def test_java_workspace_happy_path_returns_real_generation_and_compilation(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["generation_available"] is True
    assert body["project"]["files"]
    assert body["compilation"]["success"] is True
    assert body["compilation_status"] == "PASS"


def test_java_workspace_behavioral_status_is_inconclusive_without_cobol_runtime(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    assert body["behavioral_status"] == "INCONCLUSIVE"
    assert body["behavioral"]["real_cobol_execution"] is False


def test_java_workspace_self_repair_is_not_available_without_a_provider(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()

    assert body["quality_loop_available"] is False
    assert "provider" in body["quality_loop_reason"].lower()
    assert "not configured" in body["quality_loop_reason"].lower()


def test_java_workspace_repair_history_is_empty_never_fabricated(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()

    assert body["iteration_count"] == 0
    assert body["repair_count"] == 0
    assert body["iterations"] == []
    assert body["final_status"] is None
    assert body["stop_reason"] is None
    assert body["loop_state"] is None


def test_java_workspace_human_review_state_is_honestly_empty(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()

    assert body["human_review_required"] is False
    assert body["human_review_checkpoints"] == []


def test_java_workspace_audit_history_is_honestly_empty(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()

    assert body["audit_trail"] == []


def test_java_workspace_real_candidate_identity_when_generation_succeeds(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()

    assert body["current_candidate"] is not None
    assert body["current_candidate"]["version"] == 1
    assert body["current_candidate"]["created_from_repair"] is False
    assert body["candidate_lineage"] == [body["current_candidate"]]


def test_java_workspace_no_candidate_when_architecture_unavailable(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    from app.java_modernization.errors import ArchitectureError

    def boom(bundle):
        raise ArchitectureError("no AST")

    monkeypatch.setattr("app.dataset.modernization_bundle.build_architecture", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()

    assert body["generation_available"] is False
    assert body["current_candidate"] is None
    assert body["candidate_lineage"] == []


def test_java_workspace_path_traversal_is_rejected(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "../../etc/passwd"},
    )
    assert resp.status_code == 403


def test_java_workspace_missing_workspace_is_404(monkeypatch, tmp_path):
    def mock_get(self, ws_id):
        from app.core.exceptions import ResourceNotFoundException

        raise ResourceNotFoundException(resource="workspace", identifier=str(ws_id))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 404


def test_java_workspace_missing_source_is_404(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace",
        json={"filename": "missing.cbl"},
    )
    assert resp.status_code == 404


def test_java_workspace_response_is_deterministic(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/java-workspace"

    r1 = client.post(url, json={"filename": "if_else.cbl"})
    r2 = client.post(url, json={"filename": "if_else.cbl"})
    b1, b2 = r1.json(), r2.json()
    for body in (b1, b2):
        for volatile in ("workspace", "duration_s", "command", "raw_output"):
            body["compilation"].pop(volatile, None)
    assert b1 == b2


def test_java_workspace_reuses_the_pipeline_cache_not_a_second_one(
    monkeypatch, tmp_path
):
    """Explicit proof this router shares PipelineCache with the other
    four -- one analysis serves /java-workspace and /architecture alike."""
    from app.dataset import analysis_bundle as analysis_bundle_module
    from app.api.services.pipeline_cache import get_pipeline_cache

    get_pipeline_cache().clear()
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    calls = []
    real = analysis_bundle_module.build_analysis_bundle

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr("app.api.services.pipeline.build_analysis_bundle", counting)

    workspace_id = uuid.uuid4()
    body = {"filename": "if_else.cbl"}
    client.post(
        f"/api/v1/workspaces/{workspace_id}/modernization/architecture", json=body
    )
    client.post(
        f"/api/v1/workspaces/{workspace_id}/modernization/java-workspace", json=body
    )

    assert len(calls) == 1
