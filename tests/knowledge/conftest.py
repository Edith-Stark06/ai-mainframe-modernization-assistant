"""Shared fixtures for Phase 8 #122 knowledge tests. No live services."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge import (
    EmbeddingModelId,
    KnowledgeIndex,
    KnowledgeIngestor,
    KnowledgeRetriever,
)
from app.rag.embeddings.provider import DeterministicFakeProvider

FIXTURE = Path("tests/fixtures/phase4/eligibility_rules.cbl")
FIXTURE2 = Path("tests/fixtures/phase5/complex_procedural.cbl")


@pytest.fixture(scope="session")
def elig_source() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def proc_source() -> str:
    return FIXTURE2.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def elig_ingestion(elig_source):
    return KnowledgeIngestor().ingest_program("ELIGIBILITY", elig_source)


@pytest.fixture(scope="session")
def proc_ingestion(proc_source):
    return KnowledgeIngestor().ingest_program("COMPLEXPROC", proc_source)


@pytest.fixture
def model_id() -> EmbeddingModelId:
    return EmbeddingModelId("fake", "fake-mini", "v1", 48)


@pytest.fixture
def index(model_id) -> KnowledgeIndex:
    return KnowledgeIndex(
        DeterministicFakeProvider(dimension=48, model_name="fake-mini"),
        model_id,
        workspace_id="ws-test",
    )


@pytest.fixture
def loaded_index(index, elig_ingestion) -> KnowledgeIndex:
    index.add(elig_ingestion.chunks)
    return index


@pytest.fixture
def retriever(loaded_index) -> KnowledgeRetriever:
    return KnowledgeRetriever(loaded_index, allowed_source_ids={"ELIGIBILITY"})
