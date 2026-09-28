"""API tests for the JCL analysis endpoint."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.ingestion.workspace import WorkspaceManager
from app.main import app

client = TestClient(app)

_JCL_SOURCE = """\
//PAYROLL  JOB (ACCT),'RUN PAYROLL'
//STEP01   EXEC PGM=PAYCALC
//INFILE   DD DSN=PAY.INPUT,DISP=SHR
"""

_JCL_NO_JOB = """\
//STEP01   EXEC PGM=PAYCALC
"""


def _mock_workspace(monkeypatch, tmp_path) -> None:
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)


def test_jcl_analysis_endpoint_happy_path(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "payroll.jcl").write_text(_JCL_SOURCE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/jcl/analyze",
        json={"filename": "payroll.jcl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["program"]["job"]["name"] == "PAYROLL"
    assert len(body["program"]["steps"]) == 1
    step = body["program"]["steps"][0]
    assert step["name"] == "STEP01"
    assert step["program"] == "PAYCALC"
    assert len(step["dd_statements"]) == 1
    assert step["dd_statements"][0]["name"] == "INFILE"


def test_jcl_analysis_endpoint_missing_job_statement_still_succeeds(
    monkeypatch, tmp_path
) -> None:
    """A malformed/partial job stream (no JOB line) is diagnosed, not
    rejected -- matching JclAnalysisService's own graceful-degradation
    contract."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "headless.jcl").write_text(_JCL_NO_JOB, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/jcl/analyze",
        json={"filename": "headless.jcl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["program"] is not None
    assert body["program"]["job"] is None
    assert any(d["code"] == "JCL001" for d in body["diagnostics"])


def test_jcl_analysis_endpoint_file_not_found(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/jcl/analyze",
        json={"filename": "missing.jcl"},
    )
    assert resp.status_code == 404


def test_jcl_analysis_endpoint_path_traversal(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/jcl/analyze",
        json={"filename": "../../../etc/passwd"},
    )
    assert resp.status_code == 403


def test_jcl_analysis_endpoint_hides_internal_errors(monkeypatch, tmp_path) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "payroll.jcl").write_text(_JCL_SOURCE, encoding="utf-8")

    from app.jcl.service import JclAnalysisService

    def boom(self, path):
        raise ValueError("secret internal detail")

    monkeypatch.setattr(JclAnalysisService, "analyze_file", boom)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/jcl/analyze",
        json={"filename": "payroll.jcl"},
    )
    assert resp.status_code == 500
    assert "secret" not in resp.text


def test_jcl_analysis_endpoint_unsupported_statement_captured(
    monkeypatch, tmp_path
) -> None:
    _mock_workspace(monkeypatch, tmp_path)
    src = (
        "//PAYROLL  JOB (ACCT),'RUN PAYROLL'\n"
        "//STEP01   EXEC PGM=PAYCALC\n"
        "//         SET PARM=TEST\n"
    )
    (tmp_path / "with_set.jcl").write_text(src, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/jcl/analyze",
        json={"filename": "with_set.jcl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["program"]["unsupported"]) == 1
    assert body["program"]["unsupported"][0]["operation"] == "SET"
