"""
Retrieval Evaluation.

Purpose:
    Measure whether retrieval puts the facts needed to answer a question in
    front of the model. Each case is a question plus *evidence*: text that must
    appear in the retrieved chunks. No language model is involved, so the
    measurement is deterministic, free and repeatable -- which is what lets a
    retrieval change be shown to help rather than judged by eye.

Responsibilities:
    - :class:`EvalCase` / :func:`load_cases` -- the question set.
    - :func:`evaluate_retrieval` -- run any ``search(question, top_k)`` callable
      over the cases and score it.
    - :class:`RetrievalReport` -- per-case and aggregate results.
    - ``python -m app.rag.evaluation`` -- print a report for the bundled sample.

Non-responsibilities:
    - Judging the wording of a generated answer (see ``scripts/evaluate_chat.py``
      for the live, model-backed check).

Dependencies:
    - app.rag.retrieval, app.rag.ingestion, app.rag.indexing.memory

Examples:
    ::

        python -m app.rag.evaluation --mode hybrid --top-k 5

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.rag.retrieval.models import RetrievalResult

__all__ = [
    "CaseResult",
    "EvalCase",
    "RetrievalReport",
    "evaluate_retrieval",
    "load_cases",
]

Search = Callable[[str, int], Sequence[RetrievalResult]]

DEFAULT_CASES = Path("tests/fixtures/rag_eval/sales_report_cases.json")


@dataclass(frozen=True)
class EvalCase:
    """A question and the evidence the retrieved chunks must contain."""

    id: str
    question: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class CaseResult:
    """
    Outcome of one case.

    Attributes:
        case: The case.
        ranks: ``{evidence: 1-based rank of the first chunk containing it}``;
            ``None`` when no retrieved chunk contains it.
    """

    case: EvalCase
    ranks: dict[str, int | None]

    @property
    def evidence_recall(self) -> float:
        """Fraction of the case's evidence that was retrieved."""
        found = sum(1 for r in self.ranks.values() if r is not None)
        return found / len(self.ranks) if self.ranks else 1.0

    @property
    def complete(self) -> bool:
        """``True`` when *all* of the evidence was retrieved."""
        return all(r is not None for r in self.ranks.values())

    @property
    def missing(self) -> list[str]:
        """Evidence that no retrieved chunk contained."""
        return [e for e, r in self.ranks.items() if r is None]

    @property
    def reciprocal_rank(self) -> float:
        """1/rank of the best-placed evidence (0 if none was retrieved)."""
        found = [r for r in self.ranks.values() if r is not None]
        return 1.0 / min(found) if found else 0.0


@dataclass(frozen=True)
class RetrievalReport:
    """Per-case results plus aggregates."""

    top_k: int
    results: tuple[CaseResult, ...] = field(default_factory=tuple)

    @property
    def complete_rate(self) -> float:
        """Fraction of cases whose evidence was *all* retrieved."""
        return sum(r.complete for r in self.results) / max(len(self.results), 1)

    @property
    def mean_evidence_recall(self) -> float:
        """Average per-case evidence recall."""
        return sum(r.evidence_recall for r in self.results) / max(len(self.results), 1)

    @property
    def mean_reciprocal_rank(self) -> float:
        """Mean of each case's reciprocal rank."""
        return sum(r.reciprocal_rank for r in self.results) / max(len(self.results), 1)

    def format(self) -> str:
        """A readable table, worst cases visible."""
        lines = [
            f"top_k={self.top_k}  cases={len(self.results)}  "
            f"complete={self.complete_rate:.0%}  "
            f"evidence_recall={self.mean_evidence_recall:.0%}  "
            f"MRR={self.mean_reciprocal_rank:.2f}"
        ]
        for r in self.results:
            mark = "OK  " if r.complete else "MISS"
            detail = "" if r.complete else f"  missing: {r.missing}"
            lines.append(f"  {mark} {r.case.id}{detail}")
        return "\n".join(lines)


def load_cases(path: str | Path = DEFAULT_CASES) -> list[EvalCase]:
    """Read an evaluation case file (``{"cases": [{id, question, evidence}]}``)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        EvalCase(
            id=str(c["id"]),
            question=str(c["question"]),
            evidence=tuple(str(e) for e in c["evidence"]),
        )
        for c in data["cases"]
    ]


def _normalise(text: str) -> str:
    """Lower-case and collapse whitespace: COBOL pads with runs of spaces."""
    return " ".join(text.lower().split())


def evaluate_retrieval(
    search: Search, cases: Sequence[EvalCase], top_k: int
) -> RetrievalReport:
    """
    Score *search* on *cases*.

    Args:
        search: ``search(question, top_k)`` returning ranked chunks.
        cases: The questions and expected evidence.
        top_k: How many chunks each search may return.

    Returns:
        A :class:`RetrievalReport`. Evidence matching is a case- and whitespace-
        insensitive substring test against each retrieved chunk's text.
    """
    results: list[CaseResult] = []
    for case in cases:
        retrieved = list(search(case.question, top_k))[:top_k]
        texts = [_normalise(r.content) for r in retrieved]
        ranks: dict[str, int | None] = {}
        for evidence in case.evidence:
            needle = _normalise(evidence)
            ranks[evidence] = next(
                (i for i, text in enumerate(texts, 1) if needle in text), None
            )
        results.append(CaseResult(case=case, ranks=ranks))
    return RetrievalReport(top_k=top_k, results=tuple(results))


def _main() -> None:  # pragma: no cover - thin CLI over tested pieces
    from app.rag.embeddings.provider import SentenceTransformerProvider
    from app.rag.indexing.memory import InMemoryIndex
    from app.rag.ingestion import index_program
    from app.rag.retrieval.service import RetrievalService

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["vector", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    args = parser.parse_args()

    cases_path = Path(args.cases)
    program = cases_path.parent / json.loads(cases_path.read_text())["program"]
    provider = SentenceTransformerProvider()
    index = InMemoryIndex(expected_dimension=384)
    index_program(
        source_id=program.stem.upper(),
        source_text=program.read_text(encoding="utf-8"),
        source_path=program.name,
        extra_metadata={"filename": program.name},
        embedding_provider=provider,
        index=index,
    )
    if args.mode == "hybrid":
        from app.rag.retrieval.hybrid import HybridRetrievalService

        service: RetrievalService = HybridRetrievalService(provider, index)
    else:
        service = RetrievalService(provider, index)

    def search(question: str, top_k: int) -> list[RetrievalResult]:
        return service.search(question, top_k=top_k)

    print(evaluate_retrieval(search, load_cases(cases_path), args.top_k).format())


if __name__ == "__main__":  # pragma: no cover
    _main()
