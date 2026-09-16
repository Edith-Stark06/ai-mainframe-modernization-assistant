"""Phase 8 #123 grounded-chat fixtures — deterministic, no live model."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest, LLMResponse
from app.dataset.analysis_bundle import build_analysis_bundle
from app.knowledge import (
    EmbeddingModelId,
    KnowledgeIndex,
    KnowledgeIngestor,
    KnowledgeRetriever,
)
from app.rag.embeddings.provider import DeterministicFakeProvider

ELIG = Path("tests/fixtures/phase4/eligibility_rules.cbl")


@pytest.fixture(scope="session")
def elig_bundle():
    return build_analysis_bundle(
        "ELIGIBILITY", ELIG.read_text(encoding="utf-8"), tempfile.mkdtemp()
    )


@pytest.fixture(scope="session")
def retriever(elig_bundle):
    ing = KnowledgeIngestor().ingest_bundle(elig_bundle)
    idx = KnowledgeIndex(
        DeterministicFakeProvider(dimension=48), EmbeddingModelId("fake", "m", "v1", 48)
    )
    idx.add(ing.chunks)
    return KnowledgeRetriever(idx, allowed_source_ids={"ELIGIBILITY"})


def _valid_ids(prompt: str) -> list[str]:
    m = re.search(r"VALID EVIDENCE IDS\n(\[.*\])", prompt)
    return json.loads(m.group(1)) if m else []


class ScriptedAnswerProvider(LLMProvider):
    """Returns a fixed answer object; ``evidence: 'REAL'`` -> first 2 real ids."""

    def __init__(self, obj: dict) -> None:
        self.obj = obj
        self.last_prompt = ""

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.last_prompt = request.prompt
        obj = dict(self.obj)
        if obj.get("evidence") == "REAL":
            obj["evidence"] = _valid_ids(request.prompt)[:2]
        elif obj.get("evidence") == "REAL+FAKE":
            obj["evidence"] = _valid_ids(request.prompt)[:1] + ["E999"]
        return LLMResponse(text=json.dumps(obj), model="scripted")


class FailingProvider(LLMProvider):
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderUnavailableError("simulated outage")


@pytest.fixture
def scripted():
    return ScriptedAnswerProvider
