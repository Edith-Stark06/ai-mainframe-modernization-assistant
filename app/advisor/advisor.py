"""
AI Modernization Advisor (#124).

Nine explicit operations, each with a task-scoped context. The advisor
*consumes* deterministic Phase 1–5 analysis (facts are lifted straight
from the AnalysisBundle) and asks the LLM only to explain / recommend.
The response keeps DETERMINISTIC_FACT, RETRIEVED_KNOWLEDGE and
AI_RECOMMENDATION strictly separate, and every conclusion citation is
verified against the context that was actually sent.
"""

from __future__ import annotations

import tempfile

from app.advisor.context import build as build_context
from app.advisor.models import (
    AdvisorOperation,
    AdvisorResponse,
    AffectedLocation,
    Fact,
)
from app.advisor.prompt import build_advisor_prompt
from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMProviderError
from app.ai.providers.models import LLMRequest
from app.dataset.analysis_bundle import AnalysisBundle, build_analysis_bundle
from app.grounded.context import Basis, GroundedContext
from app.grounded.models import ConfidenceBand
from app.grounded.verification import (
    extract_json,
    ungrounded_identifiers,
    verify_evidence,
)
from app.knowledge.retrieval import KnowledgeRetriever

__all__ = ["ModernizationAdvisor"]

_CANNOT = "cannot be determined from the available evidence"


class ModernizationAdvisor:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        retriever: KnowledgeRetriever | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1400,
    ) -> None:
        self._provider = provider
        self._retriever = retriever
        self._temperature = temperature
        self._max_tokens = max_tokens

    # -- public operations -------------------------------------------

    def explain_program(self, bundle: AnalysisBundle) -> AdvisorResponse:
        return self._run(AdvisorOperation.EXPLAIN_PROGRAM, bundle)

    def explain_paragraph(
        self, bundle: AnalysisBundle, paragraph: str
    ) -> AdvisorResponse:
        return self._run(
            AdvisorOperation.EXPLAIN_PARAGRAPH, bundle, paragraph=paragraph
        )

    def explain_business_rule(
        self, bundle: AnalysisBundle, rule_id: str
    ) -> AdvisorResponse:
        return self._run(
            AdvisorOperation.EXPLAIN_BUSINESS_RULE, bundle, rule_id=rule_id
        )

    def identify_risks(self, bundle: AnalysisBundle) -> AdvisorResponse:
        return self._run(AdvisorOperation.IDENTIFY_RISKS, bundle)

    def recommend_strategy(self, bundle: AnalysisBundle) -> AdvisorResponse:
        return self._run(AdvisorOperation.RECOMMEND_STRATEGY, bundle)

    def explain_dependencies(self, bundle: AnalysisBundle) -> AdvisorResponse:
        return self._run(AdvisorOperation.EXPLAIN_DEPENDENCIES, bundle)

    def propose_java_architecture(self, bundle: AnalysisBundle) -> AdvisorResponse:
        return self._run(AdvisorOperation.PROPOSE_JAVA_ARCHITECTURE, bundle)

    def review_generated_java(self, bundle: AnalysisBundle) -> AdvisorResponse:
        return self._run(AdvisorOperation.REVIEW_GENERATED_JAVA, bundle)

    def answer_migration_question(
        self, bundle: AnalysisBundle, question: str
    ) -> AdvisorResponse:
        if not question or not question.strip():
            raise ValueError("question must be non-empty")
        return self._run(
            AdvisorOperation.ANSWER_MIGRATION_QUESTION, bundle, question=question
        )

    def from_source(
        self, operation: str, source_id: str, source: str, **kw: object
    ) -> AdvisorResponse:
        bundle = build_analysis_bundle(
            source_id, source, tempfile.mkdtemp(prefix="p8-advisor-")
        )
        return self._run(AdvisorOperation(operation), bundle, **kw)  # type: ignore[arg-type]

    # -- core --------------------------------------------------------

    def _run(
        self,
        operation: AdvisorOperation,
        bundle: AnalysisBundle,
        *,
        paragraph: str | None = None,
        rule_id: str | None = None,
        question: str | None = None,
    ) -> AdvisorResponse:
        # deterministic short-circuit: the advisor never asks the model
        # about a program element the analysis says does not exist.
        absent = _absent_target(operation, bundle, paragraph, rule_id)
        if absent is not None:
            return AdvisorResponse(
                operation=operation,
                conclusion=(
                    f"This {_CANNOT}: the deterministic analysis of "
                    f"{bundle.source_id} contains no {absent}."
                ),
                confidence=ConfidenceBand.NONE,
                insufficient_evidence=True,
                notes=(f"requested {absent} is absent from the analysis",),
            )

        opctx = build_context(
            operation.value,
            bundle,
            paragraph=paragraph,
            rule_id=rule_id,
            question=question,
            retriever=self._retriever,
        )
        ctx = opctx.context
        ctx.validate()  # hard provenance boundary
        prompt = build_advisor_prompt(operation.value, ctx)

        try:
            resp = self._provider.generate(
                LLMRequest(
                    prompt=prompt,
                    model=None,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
            )
            return self._assemble(operation, ctx, opctx.facts, resp.text)
        except LLMProviderError as exc:
            return AdvisorResponse(
                operation=operation,
                conclusion=f"This {_CANNOT}: the language model is unavailable ({exc}).",
                facts=tuple(opctx.facts),
                confidence=ConfidenceBand.NONE,
                affected_source_locations=_locations(opctx.facts, ()),
                basis_summary=_basis_summary(opctx.facts, (), False),
                insufficient_evidence=True,
                notes=(f"provider_failure: {exc}",),
            )

    def _assemble(
        self,
        operation: AdvisorOperation,
        ctx: GroundedContext,
        facts: list[Fact],
        text: str,
    ) -> AdvisorResponse:
        obj = extract_json(text) or {}
        conclusion = str(obj.get("conclusion", "")).strip()
        recommendation = str(obj.get("recommendation", "")).strip()
        cited = obj.get("evidence", [])
        cited_list = [str(x) for x in cited] if isinstance(cited, list) else []
        model_insufficient = bool(obj.get("insufficient_context", False))

        valid, rejected = verify_evidence(cited_list, ctx)
        ungrounded_concl = ungrounded_identifiers(conclusion, ctx)
        ungrounded_rec = ungrounded_identifiers(recommendation, ctx)

        notes: list[str] = []
        insufficient = (
            model_insufficient
            or _CANNOT in conclusion.lower()
            or not conclusion
            or bool(ungrounded_concl)
        )
        if ungrounded_concl:
            rejected = [*rejected, *ungrounded_concl]
            conclusion = (
                f"The conclusion {_CANNOT}: it referenced "
                f"{', '.join(ungrounded_concl)}, absent from the analysed program."
            )
            valid = []
        if not valid and not insufficient:
            insufficient = True
            conclusion = f"{conclusion}\n\n[grounding] Not supported by supplied evidence — {_CANNOT}."
        if rejected:
            notes.append(
                f"removed fabricated/ungrounded references: {sorted(set(rejected))}"
            )
        if ungrounded_rec:
            notes.append(
                "recommendation mentioned unverified identifiers "
                f"({', '.join(ungrounded_rec)}); treat as speculative advice only"
            )

        det = [e for e in valid if e.basis == Basis.DETERMINISTIC_FACT.value]
        retr = tuple(e for e in valid if e.basis == Basis.RETRIEVED_KNOWLEDGE.value)
        if insufficient or not valid:
            band = ConfidenceBand.NONE
        elif len(det) >= 2:
            band = ConfidenceBand.HIGH if len(valid) >= 3 else ConfidenceBand.MODERATE
        elif det:
            band = ConfidenceBand.MODERATE
        else:
            band = ConfidenceBand.LOW

        return AdvisorResponse(
            operation=operation,
            conclusion=conclusion or f"This {_CANNOT}.",
            facts=tuple(facts),
            evidence=tuple(
                e for e in valid if e.basis == Basis.DETERMINISTIC_FACT.value
            ),
            retrieved_knowledge=retr,
            recommendation=recommendation,
            confidence=band,
            affected_source_locations=_locations(facts, valid),
            basis_summary=_basis_summary(facts, valid, bool(recommendation)),
            insufficient_evidence=insufficient,
            notes=tuple(notes),
        )


def _absent_target(
    operation: AdvisorOperation,
    bundle: AnalysisBundle,
    paragraph: str | None,
    rule_id: str | None,
) -> str | None:
    if operation is AdvisorOperation.EXPLAIN_PARAGRAPH and paragraph:
        if paragraph.upper() not in {p.upper() for p in bundle.paragraphs}:
            return f"paragraph {paragraph}"
    if operation is AdvisorOperation.EXPLAIN_BUSINESS_RULE and rule_id:
        ids = {
            str(r.get("rule_id"))
            for r in (bundle.business_rules or [])
            if r.get("rule_id")
        }
        if rule_id not in ids:
            return f"business rule {rule_id}"
    return None


def _locations(facts, evidence) -> tuple[AffectedLocation, ...]:  # type: ignore[no-untyped-def]
    seen: set[tuple] = set()  # type: ignore[type-arg]
    out: list[AffectedLocation] = []
    provs = [f.provenance for f in facts] + [
        _EvProv(e) for e in evidence if e.line_start is not None or e.paragraph
    ]
    for p in provs:
        key = (
            getattr(p, "source_id", None),
            getattr(p, "line_start", None),
            getattr(p, "line_end", None),
            getattr(p, "paragraph", None),
        )
        if key in seen or key[1] is None and key[3] is None:
            continue
        seen.add(key)
        out.append(
            AffectedLocation(
                source_id=key[0] or "",
                source_path=getattr(p, "source_path", None),
                line_start=key[1],
                line_end=key[2],
                paragraph=key[3],
            )
        )
    return tuple(out)


class _EvProv:
    def __init__(self, ev) -> None:  # type: ignore[no-untyped-def]
        self.source_id = ev.source_id
        self.source_path = ev.source_path
        self.line_start = ev.line_start
        self.line_end = ev.line_end
        self.paragraph = ev.paragraph


def _basis_summary(facts, evidence, has_recommendation: bool) -> dict[str, int]:  # type: ignore[no-untyped-def]
    return {
        "DETERMINISTIC_FACT": len(facts)
        + sum(1 for e in evidence if e.basis == Basis.DETERMINISTIC_FACT.value),
        "RETRIEVED_KNOWLEDGE": sum(
            1 for e in evidence if e.basis == Basis.RETRIEVED_KNOWLEDGE.value
        ),
        "AI_RECOMMENDATION": 1 if has_recommendation else 0,
    }
