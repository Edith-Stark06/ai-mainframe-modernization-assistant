"""
Grounded chat orchestrator (#123).

    question + AnalysisBundle (+ retriever)
        -> build_context_from_bundle       (deterministic facts + RAG)
        -> GroundedContext.validate        (HARD provenance boundary)
        -> build_grounded_prompt
        -> LLMProvider.generate            (reused Phase 6/7 abstraction)
        -> parse_and_verify                (strip fabricated citations)
        -> GroundedAnswer

The model never sees a context item without provenance, and a factual
answer with no grounded evidence is downgraded to "cannot be determined".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMProviderError
from app.ai.providers.models import LLMRequest
from app.dataset.analysis_bundle import AnalysisBundle, build_analysis_bundle
from app.grounded.builder import build_context_from_bundle
from app.grounded.context import GroundedContext
from app.grounded.models import ConfidenceBand, GroundedAnswer
from app.grounded.parsing import parse_and_verify
from app.grounded.prompt import PROMPT_VERSION, build_grounded_prompt
from app.knowledge.retrieval import KnowledgeRetriever

__all__ = ["GroundedChatResult", "GroundedChat"]


@dataclass(frozen=True)
class GroundedChatResult:
    answer: GroundedAnswer
    context: GroundedContext
    prompt_version: str
    provider: str
    provider_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_version": self.prompt_version,
            "provider": self.provider,
            "provider_failed": self.provider_failed,
            "answer": self.answer.to_dict(),
            "context_provenance": self.context.provenance_manifest(),
        }


class GroundedChat:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        retriever: KnowledgeRetriever | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1200,
    ) -> None:
        self._provider = provider
        self._retriever = retriever
        self._temperature = temperature
        self._max_tokens = max_tokens

    def ask_source(
        self, question: str, source_id: str, source: str, *, work_dir: str | None = None
    ) -> GroundedChatResult:
        import tempfile

        bundle = build_analysis_bundle(
            source_id, source, work_dir or tempfile.mkdtemp(prefix="p8-chat-")
        )
        return self.ask(question, bundle)

    def ask(self, question: str, bundle: AnalysisBundle) -> GroundedChatResult:
        if not question or not question.strip():
            raise ValueError("question must be non-empty")

        context = build_context_from_bundle(question, bundle, retriever=self._retriever)
        context.validate()  # hard boundary
        prompt = build_grounded_prompt(context)

        provider_name = type(self._provider).__name__
        try:
            resp = self._provider.generate(
                LLMRequest(
                    prompt=prompt,
                    model=None,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
            )
            answer = parse_and_verify(resp.text, context)
            failed = False
        except LLMProviderError as exc:
            answer = GroundedAnswer(
                answer=(
                    "The answer cannot be determined right now: the language "
                    f"model is unavailable ({exc})."
                ),
                confidence=ConfidenceBand.NONE,
                confidence_value=0.0,
                insufficient_context=True,
                notes=(f"provider_failure: {exc}",),
            )
            failed = True

        return GroundedChatResult(
            answer=answer,
            context=context,
            prompt_version=PROMPT_VERSION,
            provider=provider_name,
            provider_failed=failed,
        )
