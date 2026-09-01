"""
Real end-to-end integration test for POST /api/v1/chat/.

Purpose:
    tests/api/test_chat.py overrides get_rag_orchestrator with a hand-rolled
    mock for every test in that file, so no committed test exercises the
    endpoint through its real dependency chain: real ChromaIndex/RetrievalService
    (with a real, non-mocked embedding search), real RAGOrchestrator, and a
    real AIAnalysisOrchestrator. That gap previously let two production bugs
    ship undetected (see app.rag.models.ImmutableDict.__deepcopy__ and
    app.rag.indexing.chroma.ChromaIndex.search's multi-key `where` filter
    handling). This test exercises the real path -- only the LLM provider is
    faked (FakeLLMProvider), matching the existing conftest.py `client`
    fixture convention -- so a regression in the real wiring fails here even
    if every unit-level test around it still passes with its own mocks.

Author:
    Claude Sonnet 5
"""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.documentation.service import DocumentationGenerationService
from app.ai.explanation.service import CodeExplanationService
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.ai.providers.fake import FakeLLMProvider
from app.api.dependencies.ai import get_ai_orchestrator
from app.api.routers.chat import get_analysis_service, get_workspace_manager
from app.core import config as cfg_mod
from app.main import app
from app.rag.embeddings.provider import DeterministicFakeProvider
from app.rag.indexing.chroma import ChromaIndex
from app.rag.models import KnowledgeChunk


@pytest.fixture
def isolated_chat_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Point the real get_rag_orchestrator dependency's ChromaIndex at an
    isolated temp directory, so this test never touches (or is polluted by)
    the shared workspace/ directory used across the rest of the test suite
    and the running application.
    """
    monkeypatch.setattr(cfg_mod.settings, "workspace_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def real_ai_orchestrator_override():
    """Override get_ai_orchestrator with a real orchestrator backed by fakes."""

    def _override():
        exp_provider = FakeLLMProvider(
            response_text="Summary:\nIt validates the input field.\n\n"
            "Explanation:\nThe program checks WS-FLAG before proceeding."
        )
        return AIAnalysisOrchestrator(
            explanation_service=CodeExplanationService(exp_provider),
            documentation_service=DocumentationGenerationService(FakeLLMProvider()),
        )

    app.dependency_overrides[get_ai_orchestrator] = _override
    yield
    app.dependency_overrides.pop(get_ai_orchestrator, None)


def _seed_chat_index(
    workspace_dir: Path, text: str, workspace_id: str, filename: str
) -> None:
    """Index one chunk into the real 'chat' ChromaDB collection, matching
    the exact persist_directory/collection_name/dimension get_rag_orchestrator
    constructs in app/api/routers/chat.py -- tagged with the same
    workspace_id/filename metadata the endpoint will filter retrieval by,
    so the seeded chunk is actually retrievable through the real multi-key
    Chroma `where` filter (workspace_id AND filename), not just present."""
    provider = DeterministicFakeProvider(dimension=384)
    index = ChromaIndex(
        persist_directory=str(workspace_dir),
        collection_name="chat",
        expected_dimension=384,
    )
    chunk = KnowledgeChunk(
        id="chunk-1",
        document_id="doc-1",
        content=text,
        chunk_index=0,
        metadata={"workspace_id": workspace_id, "filename": filename},
    )
    vector = provider.embed(text)
    from app.rag.embeddings.models import Embedding

    index.add([Embedding(chunk_id=chunk.id, vector=vector, dimension=384)], [chunk])


def test_chat_end_to_end_real_components_no_mocked_orchestrator(
    isolated_chat_index: Path,
    real_ai_orchestrator_override: None,
    tmp_path: Path,
) -> None:
    """
    Full real path: real ChromaIndex + RetrievalService + RAGOrchestrator,
    real AIAnalysisOrchestrator (FakeLLMProvider only), through the actual
    POST /api/v1/chat/ HTTP endpoint -- with include_modernization_context
    and a filename, so both the ImmutableDict deepcopy path and the
    multi-key Chroma `where` filter path are exercised together, for real.
    """
    query = "What does WS-FLAG control in this program?"
    workspace_id = str(uuid.uuid4())
    _seed_chat_index(tmp_path, query, workspace_id=workspace_id, filename="valid.cbl")

    source_dir = tmp_path.parent / "src_ws"
    source_dir.mkdir(exist_ok=True)
    (source_dir / "valid.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. VALID.\n"
    )

    class RealishWSManager:
        def get(self, ws_id: str):
            from app.ingestion.models import WorkspaceRecord

            return WorkspaceRecord(workspace_id=ws_id, path=str(source_dir))

    class EmptyAnalysisService:
        def analyze_file(self, path):
            from app.analysis.models import AnalysisResult

            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=True,
                dependencies=[],
                error=None,
                ast=None,
                ir=None,
            )

    app.dependency_overrides[get_workspace_manager] = lambda: RealishWSManager()
    app.dependency_overrides[get_analysis_service] = lambda: EmptyAnalysisService()

    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/chat/",
            json={
                "query": query,
                "workspace_id": workspace_id,
                "include_modernization_context": True,
                "filename": "valid.cbl",
            },
        )
    finally:
        app.dependency_overrides.pop(get_workspace_manager, None)
        app.dependency_overrides.pop(get_analysis_service, None)

    assert resp.status_code == 200
    data = resp.json()

    # No crash anywhere in the real chain (ImmutableDict deepcopy, multi-key
    # Chroma filter, prompt construction) -- this is the exact request shape
    # that previously always failed.
    assert data["error"] is None, data
    assert data["answer"] != ""
    assert data["modernization_data"] is not None
    assert len(data["context"]) >= 1
