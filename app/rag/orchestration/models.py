"""
RAG Orchestration Models.

Defines immutable representations for RAG requests, retrieved context, and the final combined results.
"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from app.ai.orchestration.models import AIAnalysisResult, AICapability
from app.rag.models import _freeze_metadata, _to_json_compatible
from app.rag.retrieval.models import RetrievalResult


@dataclass(frozen=True)
class RAGRequest:
    """
    Immutable representation of a RAG orchestration request.
    """

    query: str
    top_k: int = 5
    filters: Mapping[str, str | int | float | bool] = field(
        default_factory=lambda: MappingProxyType({})
    )
    ai_capabilities: frozenset[AICapability] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.query or not self.query.strip():
            raise ValueError("Query cannot be empty or whitespace-only")
        if self.top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        # Freeze the mutable fields
        object.__setattr__(self, "filters", _freeze_metadata(self.filters))
        object.__setattr__(self, "ai_capabilities", frozenset(self.ai_capabilities))

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "top_k": self.top_k,
            "filters": _to_json_compatible(self.filters),
            "ai_capabilities": [cap.name for cap in self.ai_capabilities],
        }


@dataclass(frozen=True)
class RetrievedContext:
    """
    Immutable representation of the retrieved knowledge context.
    """

    results: tuple[RetrievalResult, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results))

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class RAGResult:
    """
    Immutable representation of a RAG orchestration result.
    """

    request: RAGRequest
    context: RetrievedContext
    ai_result: AIAnalysisResult | None = None
    ai_unavailable: bool = False
    ai_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result_dict: dict[str, Any] = {
            "request": self.request.to_dict(),
            "context": self.context.to_dict(),
            "ai_unavailable": self.ai_unavailable,
            "ai_error": self.ai_error,
        }

        if self.ai_result is not None:
            # Manually map AIAnalysisResult since it doesn't have a to_dict method
            ai_res_dict: dict[str, Any] = {}
            if self.ai_result.explanation:
                ai_res_dict["explanation"] = {
                    "summary": self.ai_result.explanation.summary,
                    "explanation": self.ai_result.explanation.explanation,
                }
            else:
                ai_res_dict["explanation"] = None

            if self.ai_result.documentation:
                ai_res_dict["documentation"] = {
                    "title": self.ai_result.documentation.title,
                    "overview": self.ai_result.documentation.overview,
                    "sections": [
                        {"heading": s.heading, "content": s.content}
                        for s in self.ai_result.documentation.sections
                    ],
                }
            else:
                ai_res_dict["documentation"] = None

            ai_res_dict["context"] = _to_json_compatible(self.ai_result.context)
            result_dict["ai_result"] = ai_res_dict
        else:
            result_dict["ai_result"] = None

        return result_dict
