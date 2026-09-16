# TASK-044 — Analysis API Integration

## Objective

Expose the production AnalysisService through the FastAPI backend using the
AST, IR, and diagnostics serializers implemented in TASK-043.

This task creates the first backend API boundary between the compiler pipeline
and future frontend integration.

The existing compiler pipeline must remain unchanged.

---

## Existing Pipeline

The production analysis flow is:

COBOL source
    ↓
AnalysisService
    ↓
AnalysisResult
    ├── java_source
    ├── AST
    ├── IR
    ├── semantic diagnostics
    ├── backend diagnostics
    ├── success
    └── error
    ↓
TASK-043 serializers
    ↓
JSON-safe API response

---

## Objective

Add a FastAPI analysis endpoint that:

1. identifies a source file within an existing workspace
2. invokes AnalysisService
3. serializes AST using TASK-043
4. serializes IR using TASK-043
5. serializes diagnostics using TASK-043
6. returns generated Java source
7. returns analysis success/failure
8. follows existing API/router/schema/error-handling conventions

---

## First Step — Inspect Existing Backend

Before implementation inspect:

- app/main.py
- app/api/router.py
- app/api/
- existing route modules
- existing request/response schemas
- workspace services
- WorkspaceManager
- IngestionService
- AnalysisService
- TASK-043 serializers
- existing API tests

Do not invent conventions that already exist in the repository.

---

## API Design

Choose the endpoint path and HTTP semantics based on the actual repository
conventions.

The endpoint must remain under the existing:

/api/v1

router.

The implementation must use the existing workspace abstraction rather than
directly constructing arbitrary filesystem paths.

The source file must be resolved from the requested workspace and validated
as an allowed analysis source.

At minimum, COBOL source files should be supported using the repository's
existing supported extensions.

Do not modify upload validation.

---

## Request

Create a typed request schema if the existing API architecture uses typed
request schemas.

The request must identify:

- workspace
- source file

Use the repository's existing naming conventions.

Do not add unnecessary options that are not currently supported by
AnalysisService.

---

## Response

Create a typed response schema if the existing API architecture uses response
schemas.

The response should expose the information already available from
AnalysisResult and TASK-043 serializers.

Conceptually:

{
    "success": true,
    "workspace_id": "...",
    "filename": "...",
    "java_source": "...",
    "ast": {...},
    "ir": {...},
    "diagnostics": [...],
    "error": null
}

The exact field names must follow existing repository/API conventions.

Do not invent duplicate or conflicting diagnostic formats.

---

## Diagnostics

The API must preserve the distinction between existing diagnostic sources.

Use TASK-043 serializers.

Do not regenerate or transform diagnostics in the API layer.

The API layer should only adapt AnalysisResult into the response schema.

---

## Error Handling

Follow existing FastAPI exception handling conventions.

Handle at least:

- workspace not found
- source file not found
- unsupported source type
- analysis failure

Do not expose internal Python tracebacks to API consumers.

Do not swallow compiler errors.

Use the repository's existing error/HTTP exception conventions where available.

---

## AnalysisService

The endpoint must call:

AnalysisService

Do not duplicate the compiler pipeline in the route.

Do not directly invoke:

- lexer
- parser
- semantic analyzer
- IRBuilder
- Java generator

from the API route.

The route should depend on the production analysis service.

---

## Serialization

Use the serializers created in TASK-043.

Do not duplicate AST/IR/diagnostic serialization logic inside the API module.

The route should conceptually perform:

AnalysisService
    ↓
AnalysisResult
    ↓
TASK-043 serializers
    ↓
response schema
    ↓
FastAPI

---

## No Compiler Changes

Do not modify:

- lexer
- parser
- AST classes
- semantic analyzer
- IR classes
- IR builder
- Java backend
- diagnostic generation

---

## No Frontend Changes

Do not modify React/Stitch/frontend files.

---

## No Upload Changes

Do not redesign or modify the existing upload endpoint.

---

## Testing

Add API tests covering:

### Successful analysis

- valid workspace
- valid COBOL source
- successful response
- Java source returned
- AST returned
- IR returned
- diagnostics returned
- JSON-safe response

### Analysis with diagnostics

Verify compiler diagnostics are returned through the API.

### Missing workspace

Verify appropriate HTTP error.

### Missing source file

Verify appropriate HTTP error.

### Unsupported file

Verify appropriate HTTP error.

### Analysis failure

Verify the API returns an appropriate failure response without exposing
internal traceback details.

---

## Regression Safety

Run:

pytest -q

ruff check .

black --check .

python -m mypy app

Do not fix unrelated existing failures.

---

## Branch

Create:

feat/task-044-analysis-api

from the latest main after TASK-043 is merged.

---

## Commit

Use:

feat: add analysis api integration

---

## Patch

Generate after implementation:

git diff main...HEAD > TASK-044.patch

Verify:

git diff --stat main...HEAD
git diff --check main...HEAD

---

## Pull Request

Base:

main

Head:

feat/task-044-analysis-api

Title:

feat: Task-044 analysis API integration

Do not merge until the implementation has been reviewed.

---

## Completion Criteria

- [ ] API architecture inspected
- [ ] analysis endpoint implemented
- [ ] AnalysisService used
- [ ] TASK-043 serializers used
- [ ] typed request/response schemas added where appropriate
- [ ] success path tested
- [ ] diagnostics path tested
- [ ] workspace-not-found tested
- [ ] source-not-found tested
- [ ] unsupported source tested
- [ ] analysis failure tested
- [ ] no compiler changes
- [ ] no upload changes
- [ ] no frontend changes
- [ ] pytest passes
- [ ] ruff passes
- [ ] black passes
- [ ] mypy passes
- [ ] patch generated
- [ ] PR opened
- [ ] PR reviewed before merge