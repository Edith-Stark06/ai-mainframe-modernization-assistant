"""
Workspace Intelligence API Endpoint Tests.

Purpose:
    Integration tests for:
    - ``GET /api/v1/workspaces/{workspace_id}/inventory``
    - ``GET /api/v1/workspaces/{workspace_id}/summary``

    Tests exercise the full request/response cycle through the FastAPI
    test client against real temporary workspace directories.

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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COBOL = b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TEST.\n"
_JCL = b"//MYJOB   JOB (ACCT),'TEST',CLASS=A\n"
_COPYBOOK = b"       01 WS-RECORD.\n          05 WS-NAME PIC X(30).\n"


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a module-scoped test client."""
    with TestClient(app) as tc:
        yield tc  # type: ignore[misc]


@pytest.fixture()
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Patch ``settings.workspace_dir`` to *tmp_path* and return the root.

    This isolates API tests from the real workspace directory.
    """
    import app.workspace.inventory as inv_mod
    from app.core import config as cfg_mod

    monkeypatch.setattr(cfg_mod.settings, "workspace_dir", str(tmp_path))

    # Re-patch the router-level collaborator so it reads the patched setting
    import app.api.routers.workspace as ws_router_mod

    monkeypatch.setattr(
        ws_router_mod,
        "_inventory_builder",
        inv_mod.InventoryBuilder(),
    )

    return tmp_path


def _create_workspace(root: Path, files: dict[str, bytes]) -> str:
    """Create a workspace sub-directory with the given files and return its ID."""
    ws_id = str(uuid.uuid4())
    ws_dir = root / ws_id
    ws_dir.mkdir(parents=True)
    for filename, content in files.items():
        (ws_dir / filename).write_bytes(content)
    return ws_id


# ---------------------------------------------------------------------------
# Inventory endpoint — nominal
# ---------------------------------------------------------------------------


class TestInventoryEndpointNominal:
    """Tests for successful GET /workspaces/{id}/inventory responses."""

    def test_inventory_returns_200(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Inventory endpoint must return HTTP 200 for an existing workspace."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        response = client.get(f"/api/v1/workspaces/{ws_id}/inventory")
        assert response.status_code == 200

    def test_inventory_success_is_true(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """success field must be True on a successful response."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert body["success"] is True

    def test_inventory_workspace_id_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """workspace_id in the response must match the request path parameter."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert body["workspace_id"] == ws_id

    def test_inventory_total_files_correct(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """total_files must equal the number of files in the workspace."""
        ws_id = _create_workspace(
            workspace_root,
            {"a.cbl": _COBOL, "b.jcl": _JCL, "c.cpy": _COPYBOOK},
        )
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert body["total_files"] == 3

    def test_inventory_files_list_length_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """files list length must match total_files."""
        ws_id = _create_workspace(workspace_root, {"a.cbl": _COBOL, "b.jcl": _JCL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert len(body["files"]) == body["total_files"]

    def test_inventory_file_has_required_keys(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Each file record must contain all required metadata keys."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        required = {
            "path",
            "filename",
            "extension",
            "sha256",
            "size_bytes",
            "file_type",
            "scanned_at",
        }
        assert required.issubset(set(body["files"][0].keys()))

    def test_inventory_filename_correct(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """filename in the response must match the actual file name."""
        ws_id = _create_workspace(workspace_root, {"payroll.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert body["files"][0]["filename"] == "payroll.cbl"

    def test_inventory_file_type_is_cobol(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A .cbl file must be classified as COBOL."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert body["files"][0]["file_type"] == "COBOL"

    def test_inventory_sha256_is_64_chars(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """sha256 field in the response must be a 64-character hex string."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert len(body["files"][0]["sha256"]) == 64

    def test_inventory_scanned_at_present(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """scanned_at must be present in the response."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert body["scanned_at"]

    def test_inventory_empty_workspace_returns_empty_files(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """An empty workspace must return an empty files list."""
        ws_id = _create_workspace(workspace_root, {})
        body = client.get(f"/api/v1/workspaces/{ws_id}/inventory").json()
        assert body["total_files"] == 0
        assert body["files"] == []


# ---------------------------------------------------------------------------
# Inventory endpoint — errors
# ---------------------------------------------------------------------------


class TestInventoryEndpointErrors:
    """Tests for error responses from the inventory endpoint."""

    def test_inventory_missing_workspace_returns_404(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A non-existent workspace ID must return HTTP 404."""
        response = client.get("/api/v1/workspaces/nonexistent-ws/inventory")
        assert response.status_code == 404

    def test_inventory_404_error_envelope(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """404 response must follow the canonical error envelope."""
        body = client.get("/api/v1/workspaces/ghost-ws/inventory").json()
        assert body["success"] is False
        assert "error" in body
        assert "request_id" in body


# ---------------------------------------------------------------------------
# Summary endpoint — nominal
# ---------------------------------------------------------------------------


class TestSummaryEndpointNominal:
    """Tests for successful GET /workspaces/{id}/summary responses."""

    def test_summary_returns_200(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """Summary endpoint must return HTTP 200 for an existing workspace."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        response = client.get(f"/api/v1/workspaces/{ws_id}/summary")
        assert response.status_code == 200

    def test_summary_success_is_true(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """success field must be True on a successful summary response."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        assert body["success"] is True

    def test_summary_workspace_id_matches(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """workspace_id in the summary must match the request path parameter."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        assert body["workspace_id"] == ws_id

    def test_summary_total_files_correct(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """total_files must equal the number of files discovered."""
        ws_id = _create_workspace(workspace_root, {"a.cbl": _COBOL, "b.jcl": _JCL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        assert body["total_files"] == 2

    def test_summary_by_type_contains_cobol(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """by_type must include an entry for COBOL when .cbl files are present."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        types = {entry["file_type"] for entry in body["by_type"]}
        assert "COBOL" in types

    def test_summary_by_type_count_correct(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """COBOL count must equal the number of .cbl files uploaded."""
        ws_id = _create_workspace(
            workspace_root,
            {"a.cbl": _COBOL, "b.cbl": _COBOL, "c.jcl": _JCL},
        )
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        cobol_entries = [e for e in body["by_type"] if e["file_type"] == "COBOL"]
        assert cobol_entries[0]["count"] == 2

    def test_summary_total_size_bytes_present(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """total_size_bytes must be a non-negative integer."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        assert body["total_size_bytes"] >= 0

    def test_summary_total_size_correct(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """total_size_bytes must equal the sum of all file sizes."""
        ws_id = _create_workspace(workspace_root, {"a.cbl": _COBOL, "b.jcl": _JCL})
        expected = len(_COBOL) + len(_JCL)
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        assert body["total_size_bytes"] == expected

    def test_summary_by_type_sorted_descending(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """by_type must be sorted by count in descending order."""
        ws_id = _create_workspace(
            workspace_root,
            {
                "a.cbl": _COBOL,
                "b.cbl": _COBOL,
                "c.cbl": _COBOL,
                "d.jcl": _JCL,
                "e.cpy": _COPYBOOK,
            },
        )
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        counts = [entry["count"] for entry in body["by_type"]]
        assert counts == sorted(counts, reverse=True)

    def test_summary_scanned_at_present(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """scanned_at must be present in the summary response."""
        ws_id = _create_workspace(workspace_root, {"prog.cbl": _COBOL})
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        assert body["scanned_at"]

    def test_summary_empty_workspace(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """An empty workspace must return a valid summary with zeros."""
        ws_id = _create_workspace(workspace_root, {})
        body = client.get(f"/api/v1/workspaces/{ws_id}/summary").json()
        assert body["total_files"] == 0
        assert body["total_size_bytes"] == 0
        assert body["by_type"] == []


# ---------------------------------------------------------------------------
# Summary endpoint — errors
# ---------------------------------------------------------------------------


class TestSummaryEndpointErrors:
    """Tests for error responses from the summary endpoint."""

    def test_summary_missing_workspace_returns_404(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """A non-existent workspace ID must return HTTP 404."""
        response = client.get("/api/v1/workspaces/nonexistent-ws/summary")
        assert response.status_code == 404

    def test_summary_404_error_envelope(
        self, client: TestClient, workspace_root: Path
    ) -> None:
        """404 response must follow the canonical error envelope."""
        body = client.get("/api/v1/workspaces/ghost-ws/summary").json()
        assert body["success"] is False
        assert "error" in body
