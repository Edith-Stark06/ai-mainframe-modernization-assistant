"""
Chat quality behaviors through the real HTTP endpoints.

Purpose:
    * Re-indexing an edited file must replace the earlier chunks (they used to
      accumulate and compete with the current ones for retrieval slots).
    * A two-part question must retrieve evidence for both parts.
    * A figure in the answer that is not in the retrieved context is flagged,
      both in the answer text and in the ``ungrounded_figures`` field.

Only the LLM is faked; ingestion, Chroma, hybrid retrieval and the
orchestrator are real.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.documentation.service import DocumentationGenerationService
from app.ai.explanation.service import CodeExplanationService
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.ai.providers.fake import FakeLLMProvider
from app.api.dependencies.ai import get_ai_orchestrator
from app.api.dependencies.rag import get_embedding_provider
from app.core import config as cfg_mod
from app.ingestion.models import WorkspaceRecord
from app.ingestion.workspace import WorkspaceManager
from app.main import app
from app.rag.embeddings.provider import DeterministicFakeProvider

_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. QUALITY.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TOTAL  PIC 9(9) VALUE 0.
       01 WS-STATUS PIC X(10) VALUE SPACE.
       01 WS-TYPE   PIC X VALUE SPACE.
       01 WS-RATE   PIC 9V99 VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM CHECK-TOTAL
           PERFORM CHECK-TYPE
           STOP RUN.
       CHECK-TOTAL.
           IF WS-TOTAL >= {limit}
               MOVE 'HIGH VALUE' TO WS-STATUS
           END-IF.
       CHECK-TYPE.
           IF WS-TYPE = 'R'
               MOVE 0.10 TO WS-RATE
           END-IF.
"""

_QUESTION = (
    "At what total does the status become HIGH VALUE, and what rate applies "
    "to type R?"
)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cfg_mod.settings, "workspace_dir", str(tmp_path))
    ws = tmp_path / "src"
    ws.mkdir()
    monkeypatch.setattr(
        WorkspaceManager,
        "get",
        lambda self, ws_id: WorkspaceRecord(workspace_id=ws_id, path=str(ws)),
    )
    app.dependency_overrides[get_embedding_provider] = (
        lambda: DeterministicFakeProvider(dimension=384)
    )
    yield ws
    app.dependency_overrides.pop(get_embedding_provider, None)
    app.dependency_overrides.pop(get_ai_orchestrator, None)


def _llm(reply: str) -> None:
    def override() -> AIAnalysisOrchestrator:
        return AIAnalysisOrchestrator(
            explanation_service=CodeExplanationService(
                FakeLLMProvider(response_text=reply)
            ),
            documentation_service=DocumentationGenerationService(FakeLLMProvider()),
        )

    app.dependency_overrides[get_ai_orchestrator] = override


def _index(client: TestClient, workspace_id: str) -> dict:
    resp = client.post(
        "/api/v1/chat/index",
        json={"workspace_id": workspace_id, "filename": "quality.cbl"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _chat(client: TestClient, workspace_id: str, query: str = _QUESTION, **extra):
    resp = client.post(
        "/api/v1/chat/",
        json={
            "query": query,
            "workspace_id": workspace_id,
            "filename": "quality.cbl",
            **extra,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_reindexing_replaces_the_previous_chunks(env: Path) -> None:
    (env / "quality.cbl").write_text(_SOURCE.format(limit=50000), encoding="utf-8")
    client, ws = TestClient(app), str(uuid.uuid4())

    first = _index(client, ws)
    assert first["chunks_replaced"] == 0

    (env / "quality.cbl").write_text(_SOURCE.format(limit=75000), encoding="utf-8")
    second = _index(client, ws)
    assert second["chunks_replaced"] == first["chunks_indexed"]

    _llm("Summary: x\n\nExplanation: y")
    context = " ".join(c["content"] for c in _chat(client, ws, top_k=100)["context"])
    assert "75000" in context
    assert "50000" not in context  # the old version is gone, not competing


def test_two_part_question_retrieves_both_facts(env: Path) -> None:
    (env / "quality.cbl").write_text(_SOURCE.format(limit=50000), encoding="utf-8")
    client, ws = TestClient(app), str(uuid.uuid4())
    _index(client, ws)
    _llm("Summary: x\n\nExplanation: y")

    context = " ".join(c["content"] for c in _chat(client, ws, top_k=4)["context"])
    assert "WS-TOTAL >= 50000" in context
    assert "WS-TYPE = 'R'" in context


def test_default_top_k_is_eight(env: Path) -> None:
    (env / "quality.cbl").write_text(_SOURCE.format(limit=50000), encoding="utf-8")
    client, ws = TestClient(app), str(uuid.uuid4())
    _index(client, ws)
    _llm("Summary: x\n\nExplanation: y")
    assert len(_chat(client, ws)["context"]) == 8


def test_invented_figure_is_flagged_in_answer_and_field(env: Path) -> None:
    (env / "quality.cbl").write_text(_SOURCE.format(limit=50000), encoding="utf-8")
    client, ws = TestClient(app), str(uuid.uuid4())
    _index(client, ws)
    _llm("Summary: It turns HIGH VALUE at 7,500.\n\nExplanation: Above 7,500.")

    data = _chat(client, ws)
    assert data["ungrounded_figures"] == ["7,500"]
    assert "Figures not found in the retrieved context" in data["answer"]
    assert data["answer"].rstrip().endswith("7,500")


def test_grounded_answer_is_left_untouched(env: Path) -> None:
    (env / "quality.cbl").write_text(_SOURCE.format(limit=50000), encoding="utf-8")
    client, ws = TestClient(app), str(uuid.uuid4())
    _index(client, ws)
    _llm("Summary: HIGH VALUE at 50000 or more.\n\nExplanation: WS-TOTAL >= 50000.")

    data = _chat(client, ws)
    assert data["ungrounded_figures"] == []
    assert "Figures not found" not in data["answer"]
