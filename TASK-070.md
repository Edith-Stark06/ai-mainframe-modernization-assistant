# TASK-070 — AI RESULT SCHEMAS AND API INTEGRATION

## Objective

Integrate the existing Phase-2 AI analysis orchestration into the existing
analysis API response contract.

Task-070 exposes structured AI analysis results through the existing
`/analyze` API without creating a new endpoint.

The API must expose:

- COBOL explanation
- generated documentation
- AI analysis metadata/context where appropriate

The implementation must reuse the existing:

AST / analysis pipeline
→ Phase-1 intelligence
→ AIAnalysisOrchestrator
→ CodeExplanationService
→ DocumentationGenerationService

No AI logic may be duplicated inside the API router.

---

# Existing Capabilities

The repository already contains:

## Phase 1

- Dependency analysis
- Dependency graph
- Dependency summary
- Business rule extraction
- Business rule normalization
- Analysis API
- Correlation metadata
- Analysis status

## Phase 2

- LLM provider abstraction
- CodeExplanationService
- DocumentationGenerationService
- AIAnalysisOrchestrator

Task-070 connects the orchestration layer to the existing API.

---

# Scope

Implement typed API schemas for AI analysis results and integrate them into
the existing `AnalysisResponse`.

The existing `/analyze` endpoint remains the API entry point.

Do NOT create a new AI endpoint.

---

# API Contract

Add an optional AI result field to `AnalysisResponse`.

Recommended shape:

```json
{
  "ai_analysis": {
    "explanation": {
      "summary": "...",
      "explanation": "..."
    },
    "documentation": {
      "title": "...",
      "overview": "...",
      "sections": [
        {
          "heading": "...",
          "content": "..."
        }
      ]
    }
  }
}