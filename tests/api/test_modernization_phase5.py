"""API serialization tests for Phase 5 coverage/confidence (#115/#116)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.ingestion.workspace import WorkspaceManager
from app.main import app

client = TestClient(app)

_SIMPLE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. P5SIMPLE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY 'HELLO'.
           STOP RUN.
"""

_UNSUPPORTED = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. P5UNSUP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(7) COMP-3 VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 1 TO WS-A.
           GO TO OTHER.
           STOP RUN.
       OTHER.
           DISPLAY WS-A.
"""


def _mock_ws(monkeypatch, tmp_path) -> None:
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)


def _pipeline(tmp_path, source: str, name: str) -> dict:
    (tmp_path / name).write_text(source, encoding="utf-8")
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/pipeline",
        json={"filename": name},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_pipeline_exposes_readiness_confidence_coverage_separately(
    monkeypatch, tmp_path
) -> None:
    _mock_ws(monkeypatch, tmp_path)
    body = _pipeline(tmp_path, _SIMPLE, "s.cbl")

    # the three distinct concepts
    assert "readiness" in body
    assert "analysis_confidence" in body
    assert "analysis_coverage" in body
    assert "interpretation" in body
    assert 0.0 <= body["analysis_confidence"] <= 1.0
    assert 0.0 <= body["analysis_coverage"] <= 1.0

    # the legacy score block is still present and unchanged in shape
    assert set(body["score"]) >= {
        "complexity_score",
        "coupling_score",
        "overall_readiness",
    }
    assert body["readiness"] == body["score"]["overall_readiness"]

    # per-dimension coverage + confidence factors
    assert set(body["coverage"]["dimensions"]) == {
        "lexical",
        "parser",
        "statement",
        "ast",
        "ir",
        "control_flow",
        "dependency",
        "business_rule",
    }
    assert "overall" in body["coverage"]
    assert "unsupported_syntax" in body["coverage"]
    assert "factors" in body["confidence"]
    assert "score" in body["confidence"]


def test_pipeline_confidence_low_for_unsupported_syntax(monkeypatch, tmp_path) -> None:
    _mock_ws(monkeypatch, tmp_path)
    clean = _pipeline(tmp_path, _SIMPLE, "clean.cbl")
    unsup = _pipeline(tmp_path, _UNSUPPORTED, "unsup.cbl")

    assert unsup["analysis_confidence"] < clean["analysis_confidence"]
    assert unsup["analysis_coverage"] < clean["analysis_coverage"]
    assert unsup["coverage"]["unsupported_syntax"]["total_occurrences"] >= 1


def test_pipeline_response_is_deterministic(monkeypatch, tmp_path) -> None:
    _mock_ws(monkeypatch, tmp_path)
    a = _pipeline(tmp_path, _UNSUPPORTED, "d.cbl")
    b = _pipeline(tmp_path, _UNSUPPORTED, "d.cbl")
    assert a == b


def test_analyze_endpoint_exposes_coverage_report(monkeypatch, tmp_path) -> None:
    _mock_ws(monkeypatch, tmp_path)
    (tmp_path / "a.cbl").write_text(_UNSUPPORTED, encoding="utf-8")
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/analyze",
        json={"filename": "a.cbl"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # parser-only coverage field unchanged
    assert body["coverage"] is not None
    assert "parse_complete" in body["coverage"]
    # new rich coverage_report
    assert body["coverage_report"] is not None
    assert "dimensions" in body["coverage_report"]
    assert body["coverage_report"]["dimensions"]["statement"]["ratio"] < 1.0
