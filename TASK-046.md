# TASK-046 — Analysis Artifact & Source Context API

## Objective

Expose existing workspace source content through a frontend-ready API
while preserving the existing Analysis API contract.

This task prepares the backend for React/Stitch frontend integration.

The backend must expose only capabilities that already exist.

Do NOT invent:
- chat persistence
- artifact persistence
- websocket diagnostics
- analysis sessions
- artifact IDs
- frontend state

---

## Branch

Create:

feat/task-046-source-context-api

---

## Background

Existing backend capabilities include:

- WorkspaceManager
- workspace inventory
- AnalysisService
- AST serialization
- IR serialization
- diagnostics serialization
- Analysis API

Task-044 provides:

POST /api/v1/workspaces/{workspace_id}/analyze

Task-045 hardened that endpoint.

This task adds read access to source files already stored inside
a workspace.

---

# Required Endpoint

## GET /api/v1/workspaces/{workspace_id}/files/{filename}

The endpoint must:

1. Resolve the workspace through WorkspaceManager.
2. Resolve the requested file inside the workspace.
3. Prevent path traversal.
4. Verify the file exists.
5. Return the source file content.
6. Return useful file metadata already available from the workspace.

---

# Response

Use a typed Pydantic response model following existing repository
conventions.

The response should contain only information supported by the
existing workspace/file abstractions.

At minimum:

- success
- workspace_id
- filename
- content

If existing metadata can be obtained cleanly, include:

- extension
- size_bytes
- sha256

Do not invent additional metadata.

---

# Supported Files

The source-context endpoint may read files already present in the
workspace.

Do not silently restrict the endpoint to .cbl/.cob unless existing
workspace conventions require that restriction.

Analysis itself remains restricted to:

- .cbl
- .cob

as established by Task-044.

---

# Security

The requested filename must remain inside the resolved workspace root.

Reject:

- ../outside
- ../../outside
- absolute paths
- equivalent traversal attempts

Use the same security approach established by Task-044/045.

Do not duplicate workspace-ID security logic.

WorkspaceManager remains authoritative for workspace resolution.

---

# Error Handling

Use existing repository error handling.

Expected behavior:

### Workspace not found

HTTP 404.

Use the canonical error envelope.

### File not found

HTTP 404.

Use the canonical error envelope.

### Path traversal

HTTP 422.

Use the canonical validation/error envelope.

---

# Encoding

Follow existing repository conventions for reading workspace files.

Do not silently introduce a new encoding policy.

If the repository's ingestion metadata provides encoding information,
reuse it where appropriate.

If the current workspace abstraction does not expose encoding
information, use the existing source-reading convention rather than
inventing metadata.

---

# Analysis API

Do not modify the behavior of:

POST /api/v1/workspaces/{workspace_id}/analyze

Task-045 behavior must remain intact.

The new source endpoint exists to allow the frontend to display
COBOL source independently of triggering analysis.

---

# Tests

Add tests covering:

## Successful source retrieval

- HTTP 200
- success == true
- workspace_id correct
- filename correct
- content correct

## Metadata

Verify metadata that is actually returned by the endpoint.

If sha256/size/extension are included, verify their correctness.

## Missing workspace

- HTTP 404
- canonical error envelope

## Missing file

- HTTP 404
- canonical error envelope

## Path traversal

Test:

- ../outside.cbl
- ../../outside.cbl
- absolute path

All must be rejected.

## Nested files

If nested workspace paths are supported by the repository,
verify a valid nested path works.

## JSON safety

Verify the complete response is JSON serializable.

---

# Regression

Task-045 tests must continue passing.

Do not modify unrelated compiler/parser/IR/backend tests.

---

# Validation

Run:

pytest tests/analysis -q

pytest tests/integration -q

ruff check .

black --check .

python -m mypy app

If additional documented project validation exists, run it.

---

# Files

Likely:

app/api/routers/files.py
app/api/schemas/files.py
app/api/router.py
tests/analysis/test_files_api.py

Use existing project structure if different.

Do not blindly create duplicate abstractions.

---

# Commit

Commit:

feat: add workspace source context api

---

# Patch

Generate:

TASK-046.patch

---

# Pull Request

Create:

feat: Task-046 workspace source context API

Include:

- implementation summary
- endpoint
- security behavior
- tests
- validation results
- known unrelated failures

---

# Important

DO NOT MERGE.

Stop after:

1. implementation
2. tests
3. validation
4. commit
5. TASK-046.patch generation
6. PR creation

The implementation will be reviewed before merge.