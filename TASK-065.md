# TASK-065 — PHASE-1 INTELLIGENCE INTEGRATION AND HARDENING

## Objective

Complete Phase 1 of the Mainframe Modernization Assistant by validating the
integration of:

- Dependency analysis
- Dependency graph
- Dependency summary
- Business rule extraction
- Business rule normalization
- Business rule API representation

through the existing analysis service and `/analyze` API.

Task-065 is an integration and hardening task.

It must NOT introduce a new intelligence subsystem.

The goal is to establish a stable Phase-1 contract before beginning the
AI/LLM/RAG capabilities.

---

# Phase-1 PIPELINE

The expected pipeline is:

COBOL source
    ↓
Parser / AST
    ↓
Analysis service
    ├── Dependency analysis
    │      ├── dependency graph
    │      └── dependency summary
    │
    └── Business rule analysis
           ├── extraction
           └── normalization
    ↓
Analysis API
    ↓
JSON response

Both intelligence capabilities must coexist without breaking the existing
compiler/analysis functionality.

---

# PREREQUISITES

The following tasks MUST be merged into `main`:

- Task-054 — Dependency Graph foundation
- Task-055 — Workspace dependency resolution
- Task-056 — Dependency analysis summary
- Task-057 — Dependency summary API integration
- Task-058 — Dependency graph API representation
- Task-059 — Dependency graph/API hardening
- Task-061 — BusinessRule domain model
- Task-062 — BusinessRuleExtractor
- Task-063 — BusinessRule normalization
- Task-064 — Business Rule API integration

Before implementation:

```text
git fetch origin
git checkout main
git pull origin main