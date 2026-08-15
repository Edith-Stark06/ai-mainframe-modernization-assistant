# TASK-048 — Analysis Execution Correlation

## Objective

Add a server-generated execution identifier to the existing analysis API response so that each analysis request can be uniquely correlated by the frontend and future observability layers.

The identifier is correlation metadata only.

Do not introduce persistence, asynchronous execution, background jobs, WebSockets, chat state, artifact storage, or database models.

---

## Current Backend Context

The current synchronous analysis flow is:

COBOL source
→ lexer
→ parser
→ semantic analysis
→ IR construction
→ Java generation
→ serialized AnalysisResponse

The existing endpoint is:

POST /api/v1/workspaces/{workspace_id}/analyze

The current typed response contains:

- success
- workspace_id
- filename
- java_source
- ast
- ir
- diagnostics
- error

`AnalysisService` remains stateless.

---

# Scope

## 1. Add an execution identifier

Generate a new unique identifier for every accepted analysis request.

Use the Python standard library `uuid` module.

Recommended representation:

```python
analysis_id: str