# TASK-003

# Title

Enterprise File Ingestion Pipeline

---

## Context

Implement the enterprise-grade file ingestion layer for the AI-Powered Mainframe Modernization Assistant.

This module is responsible for accepting uploaded mainframe assets and preparing them for parsing.

It must support:

- COBOL
- Copybooks
- JCL
- ZIP archives

Do NOT implement parsing.

Only ingestion.

---

## Read First

Before implementation read:

AGENTS.md

PROJECT_SPEC.md

ROADMAP.md

CONTRIBUTING.md

---

## Create

app/ingestion/

models.py

validator.py

metadata.py

detector.py

workspace.py

uploader.py

service.py

app/api/routers/upload.py

tests/ingestion/

---

## Workspace

Implement:

WorkspaceManager

Responsibilities:

- create workspace
- delete workspace
- workspace metadata
- unique UUID
- timestamp

---

## Upload

Support:

- .cbl
- .cob
- .cpy
- .jcl
- .txt
- .zip

Reject unsupported extensions.

---

## Validation

Validate:

- extension
- size
- duplicate filename
- empty file

---

## Encoding Detection

Detect

UTF-8

ASCII

UTF-16

EBCDIC (basic detection only)

---

## Metadata

Extract

filename

extension

size

sha256

encoding

workspace id

created timestamp

---

## API

POST

/api/v1/upload

Return

workspace id

uploaded files

metadata

---

## Tests

Workspace

Upload

Validation

Metadata

Encoding

API

---

## Git

Branch

feature/upload-api

Commit

feat(ingestion): implement enterprise file ingestion pipeline

Push

feature/upload-api

Create Pull Request

Title

feat(ingestion): implement enterprise file ingestion pipeline

Description

## Summary

Implements enterprise file ingestion.

Features

- Workspace Manager
- Upload API
- Validation
- Encoding Detection
- Metadata Extraction

Closes #5

---

## Constraints

Do NOT implement parser.

Do NOT modify existing architecture.

Do NOT modify unrelated files.

Only implement the ingestion pipeline.

Wait for review.