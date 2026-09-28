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
    # task #stage48: cloud_readiness is a new top-level key, present
    # whenever the router can re-read the source (as it can here) --
    # see tests/api/test_modernization_intelligence.py's own dedicated
    # cloud-readiness test below for its content. invoked_by_jobs (JCL
    # correlation follow-on) is always present, empty when no .jcl file
    # in the workspace invokes this program -- see its own dedicated
    # test below.
    assert set(body) == {
        "business_rules",
        "risks",
        "strategies",
        "cloud_readiness",
        "invoked_by_jobs",
    }
    assert body["invoked_by_jobs"] == []

    assert len(body["business_rules"]) == 2  # then + else
    rule = body["business_rules"][0]
    assert rule["rule_id"].startswith("BR-")
    assert rule["category"]
    assert rule["actions"][0]["kind"] == "ASSIGN"
    assert 0.0 <= rule["confidence"] <= 1.0

    assert any(s["is_primary"] for s in body["strategies"])
    assert sum(1 for s in body["strategies"] if s["is_primary"]) == 1


def test_intelligence_endpoint_cloud_readiness_field(monkeypatch, tmp_path) -> None:
    """Task #stage48: the endpoint re-reads the source file itself (the
    router's own job, since ``AnalysisResult`` does not retain the raw
    text) and passes it through, so ``cloud_readiness`` is populated,
    not omitted, for an ordinary successful request."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "elig.cbl").write_text(_SOURCE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence",
        json={"filename": "elig.cbl"},
    )
    assert resp.status_code == 200
    cloud = resp.json()["cloud_readiness"]
    assert cloud is not None
    assert cloud["tier"] in {
        "CLOUD_READY",
        "NEEDS_REFACTORING",
        "REQUIRES_REARCHITECTURE",
        "NOT_RECOMMENDED",
    }
    assert cloud["rationale"]
    assert cloud["evidence"]
    assert 0.0 <= cloud["confidence"] <= 1.0

    # This fixture has no EXEC SQL/CICS/DLI/VSAM at all -- the most
    # straightforward possible tier.
    assert cloud["tier"] == "CLOUD_READY"


def test_intelligence_endpoint_cloud_readiness_omitted_on_reread_failure(
    monkeypatch, tmp_path
) -> None:
    """Task #stage48: if the router's own second read of the source (for
    cloud readiness -- ``AnalysisResult`` does not retain the raw text)
    hits an OSError, the endpoint must still succeed with
    ``cloud_readiness: null`` rather than a 500 -- the first read, inside
    ``AnalysisService.analyze_file``, is unaffected."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "elig.cbl").write_text(_SOURCE, encoding="utf-8")

    from pathlib import Path

    real_read_text = Path.read_text
    call_count = {"n": 0}

    def flaky_read_text(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return real_read_text(self, *args, **kwargs)
        raise OSError("simulated transient re-read failure")

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence",
        json={"filename": "elig.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cloud_readiness"] is None
    # Everything that does not depend on the raw source text is unaffected.
    assert len(body["business_rules"]) == 2


def test_intelligence_endpoint_invoked_by_jobs_correlation(
    monkeypatch, tmp_path
) -> None:
    """Follow-on to task #stage46/#stage48: a .jcl file in the same
    workspace whose EXEC PGM= matches this program's PROGRAM-ID (ELIG)
    must be surfaced as invoked_by_jobs, not silently ignored."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "elig.cbl").write_text(_SOURCE, encoding="utf-8")
    (tmp_path / "run_elig.jcl").write_text(
        "//RUNELIG  JOB (ACCT),'RUN ELIG'\n"
        "//STEP01   EXEC PGM=ELIG\n"
        "//INFILE   DD DSN=ELIG.INPUT,DISP=SHR\n",
        encoding="utf-8",
    )

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/intelligence",
        json={"filename": "elig.cbl"},
    )
    assert resp.status_code == 200
    invoked_by_jobs = resp.json()["invoked_by_jobs"]
    assert len(invoked_by_jobs) == 1
    invocation = invoked_by_jobs[0]
    assert invocation["jcl_filename"] == "run_elig.jcl"
    assert invocation["job_name"] == "RUNELIG"
    assert invocation["step_name"] == "STEP01"
    assert invocation["line"] == 2


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
