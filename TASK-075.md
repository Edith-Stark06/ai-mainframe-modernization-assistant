# TASK-075 — Embedding / Indexing

## Phase
Phase 3 — Knowledge / RAG

## Objective

Introduce the embedding and indexing abstraction required to convert KnowledgeChunk objects into searchable vector representations.

## Requirements

### 1. Embedding Provider

Create a provider abstraction independent of any specific embedding vendor.

The interface must support:

- embedding one chunk
- embedding multiple chunks
- deterministic test providers

### 2. Embedding Result

Define a structured embedding result containing:

- chunk identifier
- vector
- metadata

### 3. Configuration

Embedding configuration must support:

- provider selection
- model identifier
- dimensions where applicable

### 4. Index Abstraction

Create a provider-independent index interface supporting:

- add
- update
- delete
- lookup
- existence checks

### 5. Deterministic Fake Provider

Provide an offline fake embedding provider for tests.

Tests must not require:

- network access
- API keys
- external services

### 6. Validation

Validate:

- vector dimensions
- chunk identifiers
- empty content
- invalid provider responses

### 7. Error Handling

Provider failures must produce explicit domain/application errors.

Do not silently discard embedding failures.

### 8. Tests

Cover:

- single embedding
- batch embedding
- deterministic fake embeddings
- vector dimensions
- provider failure
- invalid vectors
- indexing
- updates
- deletes
- duplicate IDs
- ordering
- serialization

## Scope

Do not implement ChromaDB-specific persistence yet.

That belongs to TASK-076.

## Validation

pytest
ruff check .
black --check .
python -m mypy app
git diff --check