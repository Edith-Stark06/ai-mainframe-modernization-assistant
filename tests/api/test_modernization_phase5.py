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

# Malformed PROCEDURE DIVISION: the parser recovers, produces no
# statements, and the legacy scorer still reports a high readiness from
# the near-empty flow. Phase 5 must expose that as insufficient data.
_PARSER_FAILURE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. P5FAIL.
       PROCEDURE DIVISION.
       MAIN-PARA
           MOVE MOVE TO TO
           IF IF THEN
           PERFORM
           DISPLAY
           STOP RUN
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
    assert "insufficient_data" in body
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


def test_pipeline_parser_failure_is_explicitly_insufficient_data(
    monkeypatch, tmp_path
) -> None:
    """
    End-to-end contract (Phase 5 review fix #2): a parser-failure result
    must expose readiness, analysis_confidence, analysis_coverage,
    insufficient_data and interpretation, and the interpretation must
    explicitly prevent the high legacy readiness from being read as a
    trustworthy recommendation.
    """
    _mock_ws(monkeypatch, tmp_path)
    body = _pipeline(tmp_path, _PARSER_FAILURE, "fail.cbl")

    # all five fields are present in the serialized response
    for key in (
        "readiness",
        "analysis_confidence",
        "analysis_coverage",
        "insufficient_data",
        "interpretation",
    ):
        assert key in body, f"missing '{key}' in pipeline response"

    # the legacy scorer still produces a high readiness from the near-empty flow
    assert body["readiness"] == body["score"]["overall_readiness"]
    assert body["readiness"] >= 0.7

    # ...but confidence and coverage are near zero and it is flagged
    assert body["analysis_confidence"] <= 0.15
    assert body["analysis_coverage"] <= 0.15
    assert body["insufficient_data"] is True

    # ...and the interpretation makes the high readiness un-actionable
    interp = body["interpretation"].lower()
    assert "insufficient data" in interp
    assert "must not" in interp
    # it explicitly names the readiness number and says it is not a recommendation
    assert "recommendation" in interp

    # high readiness + near-zero confidence/coverage is represented as
    # insufficient data, not as a strong modernization recommendation
    assert not (
        body["readiness"] >= 0.7
        and body["analysis_confidence"] >= 0.5
        and body["insufficient_data"] is False
    )


def test_pipeline_clean_program_is_not_insufficient_data(monkeypatch, tmp_path) -> None:
    _mock_ws(monkeypatch, tmp_path)
    body = _pipeline(tmp_path, _SIMPLE, "ok.cbl")
    assert body["insufficient_data"] is False
    assert "insufficient data" not in body["interpretation"].lower()


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
