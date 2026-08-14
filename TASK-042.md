# Task-042 — Production Analysis Service

## Objective

Extract the existing COBOL compilation/analysis orchestration from
`tests/integration/helpers.py` into production code under `app/analysis/`.

The goal is to create one reusable production service that the future
FastAPI API layer can call.

This task is an architectural extraction only.

**Do not change the behavior of the lexer, parser, semantic analyzer,
IR builder, or Java generator.**

---

## Existing Pipeline

The existing integration pipeline is:

COBOL Source
    ↓
CobolLexer
    ↓
ProgramParser
    ↓
SemanticAnalyzer
    ↓
IRBuilder
    ↓
Java Backend
    ↓
Java Source + Diagnostics

The production service must preserve this exact order.

---

## Files to Create

Create:

```text
app/
└── analysis/
    ├── __init__.py
    ├── models.py
    └── service.py