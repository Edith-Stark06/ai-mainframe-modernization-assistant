# TASK-045 — Analysis API Contract & Integration Hardening

## Objective

Harden the Task-044 Analysis API so that its request validation,
response contract, serialization behavior, and error handling are
stable and suitable for frontend integration.

This task builds on:

- Task-042 — AnalysisService
- Task-043 — AST / IR / Diagnostics serialization
- Task-044 — Analysis API integration

Do not redesign the compiler pipeline.

Do not implement frontend code.

Do not invent new APIs.

---

## Branch

Create and work on:

feat/task-045-analysis-api-hardening

---

## Endpoint Under Test

POST

/api/v1/workspaces/{workspace_id}/analyze

The existing Task-044 endpoint is the subject of this task.

---

## Required Inspection

Before modifying code, inspect:

- app/api/router.py
- app/api/routers/analysis.py
- app/api/schemas/analysis.py
- app/analysis/service.py
- app/analysis/models.py
- app/analysis/serializers/
- app/ingestion/workspace.py
- existing API exception/error handling
- existing API tests

Follow repository conventions.

Do not introduce a new error-handling framework.

---

# Scope

## 1. Harden AnalysisRequest

Review the existing request schema.

Ensure that:

- filename is required
- whitespace is stripped according to repository conventions
- empty/whitespace-only filenames are rejected
- validation behavior follows the project's existing Pydantic conventions

Do not add unnecessary fields.

---

## 2. Harden path validation

The analysis endpoint must continue protecting the workspace boundary.

Verify handling of:

- `../outside.cbl`
- `../../outside.cbl`
- absolute paths
- equivalent traversal forms
- valid nested paths, if the repository's workspace model permits them

The source path must remain inside the resolved workspace root.

Do not duplicate workspace-ID resolution logic.

Continue using WorkspaceManager as the authoritative workspace abstraction.

---

## 3. Harden AnalysisResponse

Review the response schema for correctness and maintainability.

Ensure:

- `success` is always present
- `workspace_id` is always present
- `filename` is always present
- `java_source` is always present according to current AnalysisResult semantics
- `ast` may be null
- `ir` may be null
- `diagnostics` is always a list
- `error` may be null

Avoid mutable default values.

Use the project's existing Pydantic version and conventions.

Do not invent additional response fields unless they are directly
supported by AnalysisResult or existing backend behavior.

---

## 4. Verify diagnostics contract

The current AnalysisResult exposes:

- semantic_diagnostics
- backend_diagnostics

The API should serialize the diagnostics currently available from
AnalysisResult.

Do NOT invent syntax diagnostics.

Do NOT modify the parser diagnostic model merely to expand this API.

Verify that:

semantic_diagnostics + backend_diagnostics

remain JSON serializable through Task-043 serialization.

---

## 5. Verify AnalysisService integration

The endpoint must continue calling:

AnalysisService.analyze_file(...)

Do not duplicate:

- lexer logic
- parser logic
- semantic analysis
- IR construction
- Java generation

inside the API route.

The API layer should remain an orchestration layer.

---

## 6. Error behavior

Verify existing behavior for:

### Workspace not found

Expected:

HTTP 404

with the repository's canonical error envelope.

### Source file not found

Expected:

HTTP 404

with the repository's canonical error envelope.

### Unsupported source extension

Supported analysis source extensions remain:

- .cbl
- .cob

Do not expand this list in this task.

Expected:

HTTP 422

using existing validation/error conventions.

### Analysis failure

If AnalysisService returns:

success=False

with an error, the API must expose the controlled failure
according to the existing Task-044 contract.

Do not leak an implementation traceback.

---

# 7. Response JSON safety

Add/maintain tests proving that a successful analysis response can be
serialized through the actual FastAPI/Pydantic response model.

Verify that:

- AST contains only JSON-compatible values
- IR contains only JSON-compatible values
- diagnostics contain only JSON-compatible values
- Java source is a string
- null values are handled correctly

Do not introduce generic `str(object)` serialization.

---

# Tests

Extend the existing analysis API tests.

At minimum verify:

## Successful analysis

- HTTP 200
- success == true
- workspace_id is correct
- filename is correct
- java_source is present
- AST is present
- IR is present
- diagnostics is a list
- error is null

## Semantic failure

- HTTP 200
- success == false
- diagnostics are present
- error behavior matches Task-044
- response remains JSON serializable

## Missing workspace

- HTTP 404
- canonical error envelope

## Missing source

- HTTP 404
- canonical error envelope

## Unsupported extension

- HTTP 422
- canonical validation/error behavior

## Empty filename

Verify request validation rejects it.

## Whitespace filename

Verify request validation rejects it.

## Path traversal

Verify attempts such as:

../outside.cbl
../../outside.cbl

are rejected.

## Absolute path

Verify an absolute path cannot escape the workspace.

## JSON serialization

Verify the complete successful response can be converted to JSON
without custom fallback serialization.

---

# Regression

Run the relevant existing tests.

Do not modify unrelated compiler/parser/IR tests.

Known unrelated failures from previous tasks must remain unrelated
unless this task directly exposes a regression.

---

# Validation

Run:

pytest tests/analysis -q

pytest tests/integration -q

ruff check .

black --check .

python -m mypy app

If the repository has additional documented validation commands,
follow them as well.

---

# Files

Modify only files necessary for this task.

Likely files:

app/api/routers/analysis.py
app/api/schemas/analysis.py
tests/analysis/test_api.py

Do not create frontend files.

Do not modify compiler/backend/parser behavior unless strictly
required to preserve the existing API contract.

---

# Commit

Commit with:

fix: harden analysis api contract

---

# Patch

Generate:

TASK-045.patch

The patch must contain the complete Task-045 change.

---

# Pull Request

Create:

feat: Task-045 analysis API hardening

Include:

- objective
- implementation summary
- tests executed
- validation results
- any known unrelated failures

---

# Important

Do NOT merge the PR.

Stop after:

1. implementation
2. tests
3. validation
4. commit
5. TASK-045.patch generation
6. PR creation

The patch will be reviewed before merge.