# Phase 8 — Provenance-first RAG + Grounded AI (#122 / #123 / #124)

```
COBOL / analysis artifacts
        │  app.dataset.analysis_bundle.build_analysis_bundle   (reused — no re-analysis)
        ▼
#122  app/knowledge/   ── KnowledgeIngestor -> KnowledgeChunk[]   (Provenance ENFORCED)
        │                  KnowledgeIndex (embeddings + deterministic store)
        │                  KnowledgeRetriever (hard project scope)
        ▼
#123  app/grounded/    ── GroundedContext (3 lanes, per-item provenance)
        │                  .validate()  ── HARD BOUNDARY ── no anonymous context
        │                  build_grounded_prompt -> LLMProvider -> parse_and_verify
        │                  -> GroundedAnswer  (verified citations; ungrounded -> "cannot determine")
        ▼
#124  app/advisor/     ── 9 task-scoped operations
                           AdvisorResponse: facts | evidence | retrieved_knowledge | recommendation
                           (DETERMINISTIC_FACT / RETRIEVED_KNOWLEDGE / AI_RECOMMENDATION kept apart)
```

**Non-negotiable invariant:** every COBOL / AST / IR / CFG / dependency /
business-rule / risk / pattern / generated-Java / retrieved item sent to
the model retains `source_id` + provenance. No provenance → not sent. No
supporting evidence → "it cannot be determined from the available
evidence."

## #122 — knowledge ingestion (`app/knowledge/`)

| | |
|---|---|
| `Provenance` | frozen pydantic: `source_id` (required), `source_type`, `source_path`, `line_start/end`, `paragraph/section/statement/symbol`, `rule_id/risk_id/strategy_id/dependency`, `java_class/method`, `artifact_version`, `analysis_version`. `validate_complete()` rejects source-less / version-less / inverted-span. `citation()` renders a non-fabricated reference. |
| `KnowledgeChunk` | frozen; deterministic `sha256` id from `(source_id, artifact_version, chunk_type, location, content)`; `content_hash` verified; provenance validated on construction. |
| chunkers | COBOL → division + paragraph (real line spans); 1 chunk per business rule / risk / dependency / strategy+pattern; CFG region per paragraph; IR per function; generated Java per class/method. Deterministic. |
| `KnowledgeIngestor` | `AnalysisBundle` → chunks; provenance-validated, deduped; `rejected` list, never a silent anonymous chunk. |
| `EmbeddingModelId` | `provider/model/version/dimension` → `identity` hash; part of `index_identity` so two models' vectors never mix. |
| `KnowledgeIndex` | deterministic in-memory cosine store (no production vector DB); rejects wrong-dimension vectors and foreign-workspace chunks; `search` returns `RetrievedChunk` = chunk + provenance + score + `citation()`. |
| `KnowledgeRetriever` | fixed `allowed_source_ids` scope — a query cannot pull a chunk from another project/workspace; filter by `source_id / source_type / chunk_type / paragraph / section / rule_id / risk_id / severity / java_class / …`. |

## #123 — grounded chat (`app/grounded/`)

- `GroundedContext` — `source_context` / `analysis_context` (both `DETERMINISTIC_FACT`) + `retrieved_context` (`RETRIEVED_KNOWLEDGE`). `validate()` raises `ContextProvenanceError` before any prompt.
- System prompt contract: use only evidence, never invent identifiers, cite evidence for factual claims, distinguish fact vs inference, state when insufficient.
- `parse_and_verify` (via `verification.py`): drops citations to evidence ids that were never supplied; flags any variable / paragraph / rule / risk named in the answer that is absent from the evidence → forces `insufficient_context`. Provider failure and unparseable output resolve safely.
- `GroundedAnswer`: `answer`, verified `evidence[]`, `ConfidenceBand` (evidence-coverage label — **not** a probability), `insufficient_context`, `rejected_claims`, `basis_breakdown`.

## #124 — modernization advisor (`app/advisor/`)

- 9 operations: `explain_program`, `explain_paragraph`, `explain_business_rule`, `identify_risks`, `recommend_strategy`, `explain_dependencies`, `propose_java_architecture`, `review_generated_java`, `answer_migration_question`.
- Each builds a **task-scoped** context (no whole-repo dumps). `explain_paragraph` / `explain_business_rule` short-circuit to "cannot determine" — **without calling the model** — when the element is absent from the analysis.
- `AdvisorResponse`: `facts[]` (deterministic, from the `AnalysisBundle`, never from the LLM), verified `evidence[]`, `retrieved_knowledge[]`, `recommendation` (`AI_RECOMMENDATION` — may reason beyond evidence, must not assert nonexistent program elements), `confidence` (band), `affected_source_locations[]`, `basis_summary`.

## Reuse (nothing duplicated / redesigned)

`app.dataset.analysis_bundle` (Phase 1–5), `app.ai.providers` (LLM abstraction, Phase 6/7), `app.rag.embeddings.provider` (`EmbeddingProvider` / `DeterministicFakeProvider`). Parser / AST / IR / CFG / dependency / business-rule / risk / strategy / Java generator are **consumed, not modified**.

## Testing

`tests/knowledge/` (25), `tests/grounded/` (15), `tests/advisor/` (16 + 2 end-to-end). No test touches a live LLM, live embedding API, or the network — `DeterministicFakeProvider` and scripted `LLMProvider` doubles only.
