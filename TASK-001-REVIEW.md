# TASK-001-REVIEW

## Title

Address Code Review Feedback for PR #3 (FastAPI Bootstrap)

---

# Context

This task is a follow-up to TASK-001.

The FastAPI bootstrap has already been implemented.

Do NOT redesign or refactor the project.

Do NOT rename files.

Do NOT move folders.

Do NOT modify unrelated code.

Implement ONLY the review comments listed below.

---

# Read First

Before making changes, read:

- AGENTS.md
- PROJECT_SPEC.md
- CONTRIBUTING.md
- ROADMAP.md

Follow all project conventions.

---

# Scope

Modify ONLY the following areas:

- app/main.py
- app/core/config.py (if required)
- tests/
- LICENSE

Do not touch parser, AI, RAG, ingestion, services, or architecture.

---

# Required Changes

## 1. Replace Proprietary License

Current:

```python
license_info={
    "name": "Proprietary",
}
```

Replace with:

```python
license_info={
    "name": "MIT",
}
```

Also create a standard MIT LICENSE file in the project root if it does not already exist.

---

## 2. Configure CORS Properly

Current:

```python
allow_origins=["*"]
```

Replace with configuration-driven CORS.

### In config.py

Add:

```python
cors_origins: list[str] = [
    "http://localhost:3000",
]
```

### In main.py

Replace:

```python
allow_origins=["*"]
```

with

```python
allow_origins=settings.cors_origins
```

Do not change any other middleware configuration.

---

## 3. Improve Root Endpoint Response

Current response is minimal.

Return a structured response similar to:

```json
{
    "application": "AI-Powered Mainframe Modernization Assistant",
    "version": "0.1.0",
    "status": "running",
    "docs": "/docs",
    "health": "/api/v1/health"
}
```

Do not change the endpoint URL.

---

## 4. Add Health Tests

Create:

```
tests/test_health.py
```

Tests must verify:

### Test 1

GET /

Expected:

- HTTP 200
- contains application information
- contains docs endpoint
- contains health endpoint

### Test 2

GET /api/v1/health

Expected:

- HTTP 200
- status == "healthy"
- application name exists
- version exists
- timestamp exists

Use pytest and FastAPI TestClient.

---

## 5. Verify Quality

Run:

```bash
black .
ruff check .
mypy app
pytest
```

Fix any issues introduced by this task.

Do not change unrelated code to satisfy these checks.

---

# Git

Create one commit only.

Commit message:

```
test(api): complete FastAPI bootstrap review fixes
```

Push to:

```
feature/bootstrap
```

---

# Pull Request

If a Pull Request already exists:

Update it.

If no Pull Request exists:

Create one.

PR Title:

```
feat(api): bootstrap FastAPI application
```

PR Description:

```markdown
## Summary

Implements review feedback for the FastAPI bootstrap.

### Changes

- Added MIT license
- Configurable CORS
- Improved root endpoint response
- Added health endpoint tests
- Passed formatting and lint checks

Closes #1
```

Using **`Closes #1`** in the PR description will automatically close **Issue #1** when the PR is merged into `main`.

---

# Constraints

DO NOT:

- Refactor architecture
- Rename packages
- Introduce new dependencies
- Change API routes
- Modify parser code
- Modify AI modules
- Modify documentation unrelated to this task

Implement ONLY the requested review changes.

---

# Definition of Done

- MIT LICENSE added
- Configurable CORS implemented
- Root endpoint improved
- Health tests added
- black passes
- ruff passes
- mypy passes
- pytest passes
- Changes committed
- Changes pushed
- Pull Request updated (or created)