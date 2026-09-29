"""API tests for the graph export (Graphviz DOT) endpoint."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_COBOL_WITH_CALL_AND_MOVE = b"""        IDENTIFICATION DIVISION.
        PROGRAM-ID. CALL-TEST.

        DATA DIVISION.
        WORKING-STORAGE SECTION.
        01 WS-SOURCE PIC 9(5) VALUE 0.
        01 WS-TARGET PIC 9(5) VALUE 0.

        PROCEDURE DIVISION.
        MAIN-PARAGRAPH.
            CALL "CUSTOMER-SERVICE".
            MOVE WS-SOURCE TO WS-TARGET.
            STOP RUN.
"""


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as tc:
        yield tc


@pytest.fixture()
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.core import config as cfg_mod

    monkeypatch.setattr(cfg_mod.settings, "workspace_dir", str(tmp_path))
    return tmp_path


def _create_workspace(root: Path, files: dict[str, bytes]) -> str:
    ws_id = str(uuid.uuid4())
    ws_dir = root / ws_id
    ws_dir.mkdir(parents=True)
    for filename, content in files.items():
        (ws_dir / filename).write_bytes(content)
    return ws_id


def test_export_dependency_graph_dot(client: TestClient, workspace_root: Path) -> None:
    ws_id = _create_workspace(
        workspace_root, {"call_test.cbl": _COBOL_WITH_CALL_AND_MOVE}
    )
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/export/graph.dot",
        params={"filename": "call_test.cbl", "graph": "dependency"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/vnd.graphviz")
    body = resp.text
    assert body.startswith("digraph")
    assert '"CALL-TEST"' in body
    # The dependency graph's own target identifier keeps CALL's literal
    # quote marks (CALL "CUSTOMER-SERVICE"), so the DOT label escapes
    # them: \"CUSTOMER-SERVICE\" -- matching the existing
    # tests/analysis/test_api.py assertion on the same raw identifier.
    assert '\\"CUSTOMER-SERVICE\\"' in body
    assert '[label="CALL"]' in body


def test_export_data_flow_graph_dot(client: TestClient, workspace_root: Path) -> None:
    ws_id = _create_workspace(
        workspace_root, {"call_test.cbl": _COBOL_WITH_CALL_AND_MOVE}
    )
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/export/graph.dot",
        params={"filename": "call_test.cbl", "graph": "data_flow"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert '"WS-SOURCE"' in body
    assert '"WS-TARGET"' in body
    assert "READS" in body
    assert "WRITES" in body


def test_export_control_flow_graph_dot(
    client: TestClient, workspace_root: Path
) -> None:
    ws_id = _create_workspace(
        workspace_root, {"call_test.cbl": _COBOL_WITH_CALL_AND_MOVE}
    )
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/export/graph.dot",
        params={"filename": "call_test.cbl", "graph": "control_flow"},
    )
    assert resp.status_code == 200
    assert resp.text.startswith("digraph")


def test_export_invalid_graph_kind_is_422(
    client: TestClient, workspace_root: Path
) -> None:
    ws_id = _create_workspace(
        workspace_root, {"call_test.cbl": _COBOL_WITH_CALL_AND_MOVE}
    )
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/export/graph.dot",
        params={"filename": "call_test.cbl", "graph": "bogus"},
    )
    assert resp.status_code == 422


def test_export_missing_file_is_404(client: TestClient, workspace_root: Path) -> None:
    ws_id = _create_workspace(workspace_root, {})
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/export/graph.dot",
        params={"filename": "missing.cbl", "graph": "dependency"},
    )
    assert resp.status_code == 404


def test_export_path_traversal_is_403(client: TestClient, workspace_root: Path) -> None:
    ws_id = _create_workspace(workspace_root, {})
    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/export/graph.dot",
        params={"filename": "../../../etc/passwd", "graph": "dependency"},
    )
    assert resp.status_code == 403
