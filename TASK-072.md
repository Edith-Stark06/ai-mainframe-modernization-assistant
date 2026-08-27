# TASK-072 — AI Result Schemas/API

## Phase

Phase 2 — AI

## Objective

Finalize the public API contract for AI analysis results.

Task-072 exposes the normalized AI results produced by the existing Phase-2 AI pipeline through explicit, provider-independent Pydantic API schemas.

This task integrates with the work already completed in Tasks 069–071.

## Implementation Details

- **API Schemas:** Replaced the interim `AIAnalysisResponse` with a strict `AIResultResponse` schema that enforces standard payload types and leverages a discriminated union `AIArtifactResponse` based on `artifact_type`. 
- **Router Integration:** `app/api/routers/analysis.py` now maps `AIResultResponse` to the normalized output of `normalize_result()`.
- **Serialization and Clean Boundaries:** By relying on `.to_dict()` provided by `NormalizedAIResult`, internal Python types (like `ImmutableDict` and dataclasses) are seamlessly serialized before hitting Pydantic validators, ensuring no internal objects leak out into the public API boundary.
- **Fail-Safe Orchestration:** If AI generation fails (or artifacts are improperly structured), the router suppresses the AI response gracefully by returning `ai_result = None`, alongside an `INTERNAL_ERROR` status, while still fully preserving all existing Phase-1 analysis data (such as AST and IR).

## Validation & Tests

- Added full test suite in `tests/analysis/test_api.py` covering:
    1. EXPLANATION-only requests
    2. DOCUMENTATION-only requests
    3. Combined capabilities requests and deterministic ordering verification
    4. Safe handling of failed AI execution
    5. Clean, strict Pydantic payload enforcement
    6. Complete preservation of Phase-1 outputs when AI fails
- **Known Baseline Failures:** Note that 12 pre-existing failures (unrelated to Task-072 scope) exist in `tests/parser/` and `tests/ir/` within the current baseline environment. These have been kept intact to strictly obey task scoping limitations. All task-related and integration-specific tests successfully pass.