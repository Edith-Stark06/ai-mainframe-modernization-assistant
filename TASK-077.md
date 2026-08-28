# TASK-077 — Retrieval Service

## Phase
Phase 3 — Knowledge / RAG

## Objective

Implement a provider-independent retrieval service that searches indexed knowledge chunks and returns deterministic contextual results.

## Requirements

### 1. Retrieval Interface

Create a retrieval service that accepts:

- query text
- result limit
- optional metadata filters

### 2. Query Embedding

Use the embedding abstraction from TASK-075.

The retrieval layer must not depend directly on a concrete embedding provider.

### 3. Search

Search the configured knowledge index.

Return structured retrieval results containing:

- chunk ID
- content
- relevance/distance score
- metadata
- source information

### 4. Ordering

Results must have deterministic ordering.

When scores are equal, use a stable secondary ordering such as chunk ID.

### 5. Filtering

Support metadata filtering where supported by the underlying index.

### 6. Limits

Validate result limits and prevent unreasonable resource usage.

### 7. Empty Results

Empty search results must be represented cleanly.

Do not raise errors merely because no relevant knowledge was found.

### 8. Error Handling

Handle:

- embedding failure
- index unavailable
- malformed query
- invalid filters
- invalid result data

### 9. Tests

Cover:

- basic retrieval
- top-k behavior
- ordering
- tie-breaking
- metadata filtering
- empty results
- provider failures
- index failures
- deterministic repeated queries
- result serialization

## Scope

Do not generate AI responses.

That belongs to TASK-078.

## Validation

pytest
ruff check .
black --check .
python -m mypy app
git diff --check