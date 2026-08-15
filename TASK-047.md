# TASK-047 — Analysis Result Contract

## Objective

Define and implement a stable, typed response contract for the existing analysis pipeline so that the frontend can reliably consume the complete result of:

COBOL Source
→ Parser / AST
→ Semantic Analysis
→ IR
→ Java Generation
→ Diagnostics

This task is about **response contract quality and consistency**.

Do not introduce artifact persistence, chat state, WebSockets, database storage, or frontend code.

---

## Current Backend Context

The existing backend already provides:

### Analysis Service

`app/analysis/service.py`

`AnalysisService.analyze_file(...)` produces an `AnalysisResult` containing:

- generated Java source
- backend diagnostics
- semantic diagnostics
- success state
- error information
- AST
- IR

### Serializers

Task-043 provides:

- AST serialization
- IR serialization
- diagnostics serialization

under:

```text
app/analysis/serializers/