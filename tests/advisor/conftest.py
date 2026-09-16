"""Phase 8 #124 advisor fixtures — deterministic, no live model."""

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
def bundle():
    return build_analysis_bundle(
        "ELIGIBILITY", ELIG.read_text(encoding="utf-8"), tempfile.mkdtemp()
    )


@pytest.fixture(scope="session")
def retriever(bundle):
    ing = KnowledgeIngestor().ingest_bundle(bundle)
    idx = KnowledgeIndex(
        DeterministicFakeProvider(dimension=48), EmbeddingModelId("fake", "m", "v1", 48)
    )
    idx.add(ing.chunks)
    return KnowledgeRetriever(idx, allowed_source_ids={"ELIGIBILITY"})


class ScriptedAdvisor(LLMProvider):
    def __init__(self, obj: dict) -> None:
        self.obj = obj

    def generate(self, request: LLMRequest) -> LLMResponse:
        obj = dict(self.obj)
        if obj.get("evidence") == "REAL":
            ids = json.loads(
                re.search(r"VALID EVIDENCE IDS\n(\[.*\])", request.prompt).group(1)
            )
            obj["evidence"] = ids[:2]
        return LLMResponse(text=json.dumps(obj), model="scripted-advisor")


class FailingProvider(LLMProvider):
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderUnavailableError("outage")


GOOD = {
    "conclusion": "The program validates applicant age and accumulates a total.",
    "recommendation": "Extract each paragraph into a small service and name the rules.",
    "evidence": "REAL",
    "confidence": "moderate",
    "insufficient_context": False,
}
