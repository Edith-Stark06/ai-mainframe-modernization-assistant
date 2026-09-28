"""
Workspace Search API Endpoint Tests (task #stage47).

Purpose:
    Integration tests for ``GET /api/v1/workspaces/{workspace_id}/search``,
    exercising the full request/response cycle through the FastAPI test
    client against real temporary workspace directories, matching
    ``tests/workspace/test_workspace_api.py``'s own conventions
    (including its path-traversal regression coverage, shared here since
    the search endpoint uses the exact same ``_resolve_workspace_path``
    guard as inventory/summary).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_COBOL = (
    b"       IDENTIFICATION DIVISION.\n"
    b"       PROGRAM-ID. TEST.\n"
    b"       PROCEDURE DIVISION.\n"
    b"       MAIN-PARA.\n"
    b"           MOVE CUSTOMER-BALANCE TO WS-X.\n"
    b"           STOP RUN.\n"
)
_JCL = b"//MYJOB   JOB (ACCT),'TEST',CLASS=A\n//STEP1 EXEC PGM=CUSTOMER-BALANCE\n"


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a module-scoped test client."""
    with TestClient(app) as tc:
        yield tc  # type: ignore[misc]


@pytest.fixture()
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch ``settings.workspace_dir`` to *tmp_path* and return the root."""
    import app.workspace.inventory as inv_mod
    from app.core import config as cfg_mod

    monkeypatch.setattr(cfg_mod.settings, "workspace_dir", str(tmp_path))

    import app.api.routers.workspace as ws_router_mod

    monkeypatch.setattr(ws_router_mod, "_inventory_builder", inv_mod.InventoryBuilder())

    return tmp_path


def _create_workspace(root: Path, files: dict[str, bytes]) -> str:
    ws_id = str(uuid.uuid4())
    ws_dir = root / ws_id
    ws_dir.mkdir(parents=True)
    for filename, content in files.items():
        (ws_dir / filename).write_bytes(content)
    return ws_id


class TestSearchEndpointNominal:
    def test_search_returns_200(self, client: TestClient, workspace_root: Path) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        response = client.get(
            f"/api/v1/workspaces/{ws_id}/search", params={"q": "CUSTOMER-BALANCE"}
        )
        assert response.status_code == 200

    def test_search_success_is_true(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/search", params={"q": "CUSTOMER-BALANCE"}
        ).json()
        assert body["success"] is True

    def test_search_finds_match_in_cobol_file(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/search", params={"q": "CUSTOMER-BALANCE"}
        ).json()
        assert body["files_matched"] == 1
        assert len(body["matches"]) == 1
        assert body["matches"][0]["filename"] == "prog.cbl"

    def test_search_finds_matches_across_cobol_and_jcl(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL, "job.jcl": _JCL})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/search", params={"q": "CUSTOMER-BALANCE"}
        ).json()
        assert body["files_matched"] == 2
        assert {m["filename"] for m in body["matches"]} == {"prog.cbl", "job.jcl"}

    def test_search_is_case_insensitive(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/search", params={"q": "customer-balance"}
        ).json()
        assert body["files_matched"] == 1

    def test_search_no_match_returns_empty_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/search",
            params={"q": "NOTHING-LIKE-THIS-EXISTS"},
        ).json()
        assert body["matches"] == []
        assert body["files_matched"] == 0

    def test_search_query_echoed_back(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/search", params={"q": "MOVE"}
        ).json()
        assert body["query"] == "MOVE"

    def test_search_match_has_required_keys(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(
            f"/api/v1/workspaces/{ws_id}/search", params={"q": "MOVE"}
        ).json()
        required = {"filename", "path", "line", "snippet"}
        assert required.issubset(set(body["matches"][0].keys()))


class TestSearchEndpointValidation:
    def test_missing_query_param_is_422(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        response = client.get(f"/api/v1/workspaces/{ws_id}/search")
        assert response.status_code == 422

    def test_empty_query_param_is_422(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        response = client.get(f"/api/v1/workspaces/{ws_id}/search", params={"q": ""})
        assert response.status_code == 422


class TestSearchEndpointErrors:
    def test_search_missing_workspace_returns_404(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        response = client.get(
            "/api/v1/workspaces/nonexistent-ws/search", params={"q": "X"}
        )
        assert response.status_code == 404

    def test_search_404_error_envelope(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        body = client.get(
            "/api/v1/workspaces/ghost-ws/search", params={"q": "X"}
        ).json()
        assert body["success"] is False
        assert "error" in body


class TestSearchEndpointPathTraversal:
    """Shares ``_resolve_workspace_path`` with inventory/summary -- the
    same guard, exercised here too rather than assumed to carry over."""

    def test_search_encoded_dotdot_is_rejected(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        response = client.get("/api/v1/workspaces/%2e%2e/search", params={"q": "X"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_search_encoded_single_dot_is_rejected(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        response = client.get("/api/v1/workspaces/%2e/search", params={"q": "X"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
