# TASK-071 — AI RESULT CONTRACT AND NORMALIZATION

## Objective

Establish a stable, provider-independent contract for AI analysis results.

Task-070 exposed AI analysis through the `/analyze` API. Task-071 now
strengthens the internal AI result boundary so that explanation and
documentation artifacts can be consumed consistently by future capabilities.

This task is limited to result contracts and deterministic normalization.

---

## Scope

Implement:

1. A common AI artifact/result representation.
2. Explicit artifact types.
3. Deterministic normalization of AI results.
4. Stable ordering of artifacts.
5. Preservation of source/context metadata.
6. Validation of malformed or incomplete AI results.
7. API-compatible serialization support where required.
8. Comprehensive unit tests.

The implementation must remain provider-independent.

---

## Existing Pipeline

The existing pipeline is authoritative:

    LLMProvider
        ↓
    CodeExplanationService
        ↓
    DocumentationGenerationService
        ↓
    AIAnalysisOrchestrator
        ↓
    Analysis API

Task-071 must NOT bypass or duplicate this pipeline.

---

## Required Concepts

Introduce an explicit artifact type representing the supported AI outputs.

At minimum support:

- EXPLANATION
- DOCUMENTATION

The artifact representation must identify:

- artifact type
- artifact payload
- source/context metadata where applicable

Use the existing:

- CodeExplanation
- Documentation
- AIAnalysisResult

models rather than duplicating their contents unnecessarily.

---

## Normalized Result

Create a deterministic normalized representation of an AI analysis result.

Requirements:

- immutable
- typed
- provider-independent
- deterministic
- safe to serialize
- preserves artifact meaning
- preserves relevant analysis context

Artifact ordering must be deterministic regardless of the order in which
capabilities were requested.

Use the repository's existing capability ordering convention.

Do NOT depend on:

- dictionary insertion order
- set iteration order
- object memory addresses
- provider response ordering

---

## Validation

Reject invalid results such as:

- unknown artifact types
- missing required artifact payloads
- empty artifact collections
- invalid explanation objects
- invalid documentation objects

Do not silently fabricate missing AI artifacts.

If the underlying AI operation produced no successful artifact, the result
must remain an explicit failure/empty state according to the existing
orchestration contract.

---

## Context Preservation

The normalized result must preserve the relevant analysis context supplied
to the orchestrator.

Context must not be mutated during normalization.

Nested mutable structures must not leak through the normalized result.

For example:

- dependency information
- dependency summary
- dependency graph
- business rules
- diagnostics
- source metadata
- correlation information

must remain isolated from caller-side mutation where they are part of the
existing AI context contract.

Do not invent new Phase-1 fields.

---

## Immutability

The normalized result must be immutable.

Changing the original AI result after normalization must not change the
normalized representation.

Changing nested input context after normalization must not mutate the
normalized result.

---

## Determinism

Equivalent AI results must normalize to equivalent output regardless of:

- capability request ordering
- dictionary insertion ordering
- set ordering
- provider artifact ordering

Repeated normalization of equivalent input must produce the same result.

---

## API Compatibility

Task-071 must not break Task-070.

The existing:

    AnalysisResponse.ai_analysis

contract must continue to work.

Do not rename existing public API fields.

Do not remove:

- explanation
- documentation
- ai_analysis
- ai_capabilities

unless a concrete compatibility defect is demonstrated.

If API schemas need a minimal update to expose the normalized representation,
make only the smallest necessary change.

---

## Error Behavior

Normalization failures must be explicit.

Do not:

- swallow validation errors
- fabricate artifacts
- silently drop invalid artifacts
- convert provider failures into successful results

Existing `AnalysisStatus` and Task-070 error behavior must remain unchanged.

---

## Non-Goals

DO NOT implement:

- database persistence
- Redis
- ChromaDB
- RAG
- embeddings
- vector search
- frontend
- chat assistant
- modernization scoring
- flowchart generation
- new LLM providers
- external API integrations
- parser changes
- lexer changes
- AST changes
- dependency analyzer changes
- business-rule extractor changes

Do not modify Tasks 061–065 behavior.

---

## Expected Files

Likely files:

    app/ai/results/
    app/ai/results/models.py
    app/ai/results/normalization.py
    app/ai/results/__init__.py
    tests/ai/test_results.py
    TASK-071.md

Only create additional files when genuinely required.

Do not create scratch/debug/generated files.

---

## Testing

Add focused tests covering:

1. explanation artifact
2. documentation artifact
3. combined artifacts
4. artifact type validation
5. missing payload validation
6. empty result validation
7. deterministic artifact ordering
8. dictionary-order independence
9. set-order independence
10. input immutability
11. deep context isolation
12. repeated normalization determinism
13. serialization compatibility
14. Task-070 API regression

Use existing FakeLLMProvider infrastructure where appropriate.

Do not make network calls.

---

## Validation

Run:

    pytest tests/ai -q
    pytest tests/analysis/rules -q
    pytest tests/analysis/dependencies -q
    pytest tests/analysis -q
    pytest tests/integration -q
    pytest -q

Then:

    ruff check .
    black --check .
    python -m mypy app
    git diff --check

Compare any failures against origin/main.

Do not hide pre-existing failures.

---

## Diff Review

Run:

    git status
    git diff --stat
    git diff main...HEAD --stat
    git diff main...HEAD

Expected scope:

- Task-071 result contract
- Task-071 normalization
- Task-071 tests
- TASK-071.md

No unrelated changes.

---

## Branch

    feat/task-071-ai-result-contract

---

## Commit

    feat: add normalized ai result contract

---

## Pull Request

Title:

    feat: Task-071 normalized AI result contract

Base:

    main

Head:

    feat/task-071-ai-result-contract

Do not merge the PR.

---

## Definition of Done

- [x] Common AI artifact representation exists.
- [x] Explanation artifact supported.
- [x] Documentation artifact supported.
- [x] Normalized result is immutable.
- [x] Artifact ordering is deterministic.
- [x] Context is preserved.
- [x] Context is deeply isolated.
- [x] Invalid artifacts are rejected.
- [x] Empty invalid results are rejected.
- [x] Serialization is stable.
- [x] Task-070 API behavior remains compatible.
- [x] No provider-specific logic introduced.
- [x] No persistence introduced.
- [x] No frontend introduced.
- [x] Focused tests pass.
- [x] Full regression suite passes or baseline failures are documented.
- [x] Ruff passes.
- [x] Black passes.
- [x] Mypy passes.
- [x] git diff --check passes.
- [x] PR is created.
- [x] PR is OPEN.
- [x] PR is NOT MERGED.