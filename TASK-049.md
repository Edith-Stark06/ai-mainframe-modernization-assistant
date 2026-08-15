# TASK-049 — Analysis Source Metadata Contract

## Objective

Expose the existing source-file metadata alongside the analysis result so clients can identify exactly which workspace file was analyzed.

The analysis response should expose metadata that already exists in the workspace inventory:

- extension
- size_bytes
- sha256

This is a response-contract enhancement only.

Do not introduce persistence, artifact storage, file copying, database models, or new analysis execution behavior.

---

## Current Backend Context

The existing analysis endpoint is:

POST /api/v1/workspaces/{workspace_id}/analyze

The response currently contains:

- analysis_id
- success
- workspace_id
- filename
- java_source
- ast
- ir
- diagnostics
- error

The workspace inventory already tracks source-file metadata.

The source-context endpoint is:

GET /api/v1/workspaces/{workspace_id}/files/{filename:path}

Do not change the behavior of that endpoint.

---

# Scope

## 1. Define a typed source metadata model

Add a small Pydantic model representing metadata for the analyzed source file.

Suggested structure:

```python
class AnalysisSourceMetadata(BaseModel):
    extension: str
    size_bytes: int
    sha256: str