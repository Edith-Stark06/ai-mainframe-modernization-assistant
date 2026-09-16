"""
API-level tests proving the Architecture/Java/Validation/Report routes
share ONE pipeline result per (workspace, filename, content) via
``app.api.services.pipeline_cache``, per the reviewed requirement that
these four independent HTTP requests must not each independently rerun
the full analysis/modernization pipeline.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.services.pipeline_cache import get_pipeline_cache
from app.dataset import analysis_bundle as analysis_bundle_module
from app.ingestion.workspace import WorkspaceManager
from app.main import app

client = TestClient(app)

_IF_ELSE = Path("tests/golden/if_else.cbl").read_text(encoding="utf-8")
_IF_ELSE_EDITED = _IF_ELSE.replace("AGE > 18", "AGE > 21")


def _mock_workspace(monkeypatch, tmp_path) -> None:
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)


def _count_analysis_calls(monkeypatch) -> list:
    """Wrap the real build_analysis_bundle with a call counter, in both
    modules that import it by name (pipeline.py imports the function
    directly, so patching the origin module is what actually takes
    effect for callers that already hold a reference -- patch before
    any call happens in the test)."""
    calls: list = []
    real = analysis_bundle_module.build_analysis_bundle

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr("app.api.services.pipeline.build_analysis_bundle", counting)
    return calls


def setup_function() -> None:
    # the pipeline cache is a process-wide singleton -- start each test
    # from a known-empty state so tests never see another test's entries.
    get_pipeline_cache().clear()


def test_repeated_calls_to_the_same_endpoint_reuse_the_cached_result(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    calls = _count_analysis_calls(monkeypatch)

    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture"
    r1 = client.post(url, json={"filename": "if_else.cbl"})
    r2 = client.post(url, json={"filename": "if_else.cbl"})

    assert r1.status_code == r2.status_code == 200
    assert len(calls) == 1
    assert r1.json() == r2.json()


def test_different_endpoints_for_the_same_file_reuse_one_analysis(
    monkeypatch, tmp_path
):
    """The central requirement under review: Architecture, Java,
    Validation, and Report must consume the SAME underlying analysis
    for the same workspace/file, not one each."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    calls = _count_analysis_calls(monkeypatch)

    workspace_id = uuid.uuid4()
    body = {"filename": "if_else.cbl"}
    for endpoint in ("architecture", "java", "validation", "report"):
        resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/modernization/{endpoint}", json=body
        )
        assert resp.status_code == 200

    assert len(calls) == 1


def test_changed_source_file_is_never_served_a_stale_result(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    source_file = tmp_path / "if_else.cbl"
    source_file.write_text(_IF_ELSE, encoding="utf-8")
    calls = _count_analysis_calls(monkeypatch)

    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture"
    first = client.post(url, json={"filename": "if_else.cbl"})
    assert len(calls) == 1

    # the file changes on disk -- e.g. the user re-uploaded a fixed version
    source_file.write_text(_IF_ELSE_EDITED, encoding="utf-8")
    second = client.post(url, json={"filename": "if_else.cbl"})

    assert len(calls) == 2  # re-analyzed, not served from the old cache entry
    assert first.json()["architecture"] != second.json()["architecture"]


def test_identical_content_reuploaded_still_reuses_the_cache(monkeypatch, tmp_path):
    """The inverse of the previous test: re-writing the SAME content
    (e.g. a no-op re-upload) must still hit the cache -- staleness is
    about content, not about wall-clock file-write events."""
    _mock_workspace(monkeypatch, tmp_path)
    source_file = tmp_path / "if_else.cbl"
    source_file.write_text(_IF_ELSE, encoding="utf-8")
    calls = _count_analysis_calls(monkeypatch)

    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture"
    client.post(url, json={"filename": "if_else.cbl"})
    source_file.write_text(_IF_ELSE, encoding="utf-8")  # rewritten, same bytes
    client.post(url, json={"filename": "if_else.cbl"})

    assert len(calls) == 1


def test_two_workspaces_with_identical_filenames_never_cross_contaminate(
    monkeypatch, tmp_path
):
    """Workspace isolation: a cache entry keyed to workspace A must never
    be served for a request naming a different, nonexistent workspace B
    -- even when the filename is identical."""
    known_ws = uuid.uuid4()
    ws_root = tmp_path / "known"
    ws_root.mkdir()
    (ws_root / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    def mock_get(self, ws_id):
        from app.core.exceptions import ResourceNotFoundException
        from app.ingestion.models import WorkspaceRecord

        if str(ws_id) == str(known_ws):
            return WorkspaceRecord(workspace_id=str(ws_id), path=str(ws_root))
        raise ResourceNotFoundException(resource="workspace", identifier=str(ws_id))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)

    known_resp = client.post(
        f"/api/v1/workspaces/{known_ws}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )
    assert known_resp.status_code == 200

    other_ws = uuid.uuid4()
    other_resp = client.post(
        f"/api/v1/workspaces/{other_ws}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )
    assert other_resp.status_code == 404  # never silently served known_ws's cache


def test_two_real_workspaces_with_the_same_file_get_independent_cache_entries(
    monkeypatch, tmp_path
):
    """Two DISTINCT, both-valid workspaces containing byte-identical
    files must each be analyzed (and cached) under their own key -- the
    cache key includes workspace_id, so this is never a cross-workspace
    cache hit even though it produces the same result either way."""
    ws_a_root = tmp_path / "a"
    ws_b_root = tmp_path / "b"
    ws_a_root.mkdir()
    ws_b_root.mkdir()
    (ws_a_root / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    (ws_b_root / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    ws_a_id, ws_b_id = uuid.uuid4(), uuid.uuid4()

    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        root = ws_a_root if str(ws_id) == str(ws_a_id) else ws_b_root
        return WorkspaceRecord(workspace_id=str(ws_id), path=str(root))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)
    calls = _count_analysis_calls(monkeypatch)

    client.post(
        f"/api/v1/workspaces/{ws_a_id}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )
    client.post(
        f"/api/v1/workspaces/{ws_b_id}/modernization/architecture",
        json={"filename": "if_else.cbl"},
    )

    assert len(calls) == 2  # each workspace analyzed independently
    cache = get_pipeline_cache()
    assert (str(ws_a_id), "if_else.cbl") != (str(ws_b_id), "if_else.cbl")
    assert len(cache) == 2


def test_cache_does_not_hide_a_failed_analysis_on_retry(monkeypatch, tmp_path):
    """A transient analysis failure must not be remembered -- the next
    request for the same file gets a fresh attempt, not a cached error
    (there is no cached error state at all; failures simply are not
    cached, per PipelineCache's own contract)."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    real = analysis_bundle_module.build_analysis_bundle
    state = {"fail_once": True}

    def flaky(*args, **kwargs):
        if state["fail_once"]:
            state["fail_once"] = False
            raise ValueError("transient failure")
        return real(*args, **kwargs)

    monkeypatch.setattr("app.api.services.pipeline.build_analysis_bundle", flaky)

    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/architecture"
    first = client.post(url, json={"filename": "if_else.cbl"})
    second = client.post(url, json={"filename": "if_else.cbl"})

    assert first.status_code == 500
    assert second.status_code == 200  # retried successfully, not stuck on the failure
