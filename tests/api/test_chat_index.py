"""
Tests for POST /api/v1/chat/index.

Purpose:
    Verify the endpoint that closes the RAG loop: ingest a real
    workspace file into real, embedded, indexed chunks the /chat
    endpoint's own retrieval can then find. Includes one full
    round-trip test (index, then chat) proving the two endpoints
    actually agree on embedding space and metadata filters, not just
    that each one individually doesn't crash.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
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


@pytest.fixture
def isolated_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate the chat index and use the fast deterministic embedding
    provider -- these tests exercise ingestion/indexing/retrieval
    wiring, not embedding quality (see
    tests/rag/test_sentence_transformer_provider.py for that)."""
    monkeypatch.setattr(cfg_mod.settings, "workspace_dir", str(tmp_path))
    app.dependency_overrides[get_embedding_provider] = (
        lambda: DeterministicFakeProvider(dimension=384)
    )
    yield tmp_path
    app.dependency_overrides.pop(get_embedding_provider, None)


def _mock_workspace(monkeypatch, ws_path: Path) -> None:
    def mock_get(self, ws_id):
        return WorkspaceRecord(workspace_id=ws_id, path=str(ws_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)


def test_index_endpoint_happy_path(
    isolated_index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws_dir = isolated_index / "src"
    ws_dir.mkdir()
    (ws_dir / "elig.cbl").write_text(_SOURCE, encoding="utf-8")
    _mock_workspace(monkeypatch, ws_dir)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/chat/index",
        json={"workspace_id": str(uuid.uuid4()), "filename": "elig.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunks_indexed"] > 0
    assert body["chunks_rejected"] == 0
    assert "business_rule" in body["chunk_types"]
    assert "cobol_division" in body["chunk_types"]


def test_index_endpoint_file_not_found(
    isolated_index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws_dir = isolated_index / "src"
    ws_dir.mkdir()
    _mock_workspace(monkeypatch, ws_dir)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/chat/index",
        json={"workspace_id": str(uuid.uuid4()), "filename": "missing.cbl"},
    )
    assert resp.status_code == 404


def test_index_endpoint_path_traversal(
    isolated_index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws_dir = isolated_index / "src"
    ws_dir.mkdir()
    _mock_workspace(monkeypatch, ws_dir)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/chat/index",
        json={"workspace_id": str(uuid.uuid4()), "filename": "../../../etc/passwd"},
    )
    assert resp.status_code == 403


def test_index_then_chat_real_round_trip(
    isolated_index: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual point of this whole feature: index a real file, then
    ask chat a question about it, through the real (non-mocked)
    RAGOrchestrator/RetrievalService/ChromaIndex chain, and get real
    retrieved context back -- not an empty-index INSUFFICIENT_CONTEXT."""
    ws_dir = isolated_index / "src"
    ws_dir.mkdir()
    (ws_dir / "elig.cbl").write_text(_SOURCE, encoding="utf-8")
    _mock_workspace(monkeypatch, ws_dir)

    workspace_id = str(uuid.uuid4())
    client = TestClient(app)

    index_resp = client.post(
        "/api/v1/chat/index",
        json={"workspace_id": workspace_id, "filename": "elig.cbl"},
    )
    assert index_resp.status_code == 200
    assert index_resp.json()["chunks_indexed"] > 0

    def _override_ai():
        provider = FakeLLMProvider(
            response_text="Summary:\nEligibility check.\n\n"
            "Explanation:\nChecks WS-AGE against 18."
        )
        return AIAnalysisOrchestrator(
            explanation_service=CodeExplanationService(provider),
            documentation_service=DocumentationGenerationService(provider),
        )

    app.dependency_overrides[get_ai_orchestrator] = _override_ai
    try:
        chat_resp = client.post(
            "/api/v1/chat/",
            json={
                "query": "What does this program check about WS-AGE?",
                "workspace_id": workspace_id,
            },
        )
    finally:
        app.dependency_overrides.pop(get_ai_orchestrator, None)

    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert data["error"] is None, data
    assert len(data["context"]) >= 1
