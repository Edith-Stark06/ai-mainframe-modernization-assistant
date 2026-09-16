# TASK-060 — Dependency Graph API Integration Tests

## Objective

Strengthen integration and regression coverage for the dependency graph
exposed by the analysis API.

Verify the complete pipeline:

COBOL
→ Parser
→ AST
→ Dependency Analysis
→ Dependency Graph
→ Dependency Summary
→ Analysis API
→ JSON response

This task is test-focused.

## Scope

Cover:

- successful dependency graph response
- graph nodes
- graph edges
- CALL dependencies
- PERFORM dependencies
- source locations
- dependency summary + graph
- empty dependency graph
- semantic-error behavior
- internal-error behavior
- JSON serialization
- backward compatibility
- deterministic graph ordering

## Non-Goals

Do not redesign or modify:

- parser
- lexer
- AST
- DependencyAnalyzer
- DependencyGraph domain models
- workspace resolution
- DependencyAnalysisSummary
- API schemas
- frontend
- LLM
- RAG

Production changes are not expected.

If a genuine defect is discovered, make only the smallest correction
required and add a regression test.

## Required Tests

### 1. Successful graph

Verify:

- success is true
- dependency_graph is present
- nodes are present
- edges are present when dependencies exist

### 2. Nodes

Verify:

- canonical root identifier
- dependency target identifiers

### 3. CALL

Verify:

dependency_type == "CALL"

and correct source and target.

### 4. PERFORM

Verify:

dependency_type == "PERFORM"

and correct source and target.

### 5. Source location

Verify:

- type
- line
- column
- offset
- filename

Do not hard-code environment-specific absolute paths.

### 6. Summary + graph

Verify both can appear together.

Where guaranteed:

summary.node_count == len(graph.nodes)
summary.edge_count == len(graph.edges)

### 7. Empty graph

Verify the established domain representation for a valid program
with no dependencies.

### 8. Semantic errors

Verify existing status/error behavior and graph availability when
the AST remains available.

### 9. Internal errors

Verify dependency_graph is None when analysis fails before graph creation.

### 10. JSON

Verify:

- CALL
- PERFORM

are serialized as strings.

No domain objects or enums leak into JSON.

### 11. Backward compatibility

Verify existing AnalysisResponse fields remain intact.

### 12. Determinism

Repeated equivalent analysis must produce stable node and edge ordering.

## Validation

Run:

pytest tests/analysis/dependencies -q
pytest tests/analysis -q
pytest tests/integration -q
pytest -q
ruff check .
black --check .
python -m mypy app
git diff --check

Compare failures against origin/main.

## Expected Files

- tests/analysis/test_api.py or appropriate existing integration location
- TASK-060.md

No unrelated changes.

## Branch

feat/task-060-dependency-graph-integration-tests

## Commit

test: add dependency graph api integration coverage

## Pull Request

Title:

test: Task-060 dependency graph API integration coverage

Base: main

Do not merge.

## Definition of Done

- all required integration coverage exists
- tests pass
- static checks pass
- no unrelated changes
- TASK-060.md exists
- PR exists and is OPEN
- PR is NOT MERGED