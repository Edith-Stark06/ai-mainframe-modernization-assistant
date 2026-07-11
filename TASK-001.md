# TASK-001

## Title

Bootstrap FastAPI Backend

## Context

This repository follows Clean Architecture.

Do NOT change the project structure.

Read these files first:

- AGENTS.md
- PROJECT_SPEC.md
- ROADMAP.md
- CONTRIBUTING.md

## Objective

Implement the FastAPI bootstrap.

Create:

app/main.py

app/api/router.py

app/api/routers/health.py

app/api/schemas/base.py

app/api/schemas/health.py

tests/test_health.py

## Requirements

- Python 3.12+
- FastAPI
- Pydantic v2
- Loguru
- Absolute imports
- Type hints
- Docstrings

## Acceptance Criteria

GET /

GET /docs

GET /api/v1/health

All tests pass.

Do not modify unrelated files.

Generate production-quality code.