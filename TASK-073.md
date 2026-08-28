# TASK-073 — Knowledge-Base Model

## Phase
Phase 3 — Knowledge / RAG

## Objective

Introduce the domain model for representing knowledge-base documents and their associated chunks/metadata.

The model must provide a stable, provider-independent representation that can be used by later chunking, embedding, indexing, ingestion, retrieval, and RAG orchestration tasks.

## Requirements

### 1. Knowledge Document

Create an immutable domain representation for a knowledge-base document.

The document should support:

- unique document identifier
- source/file name
- document type
- source path or source reference
- content
- metadata
- deterministic representation

### 2. Knowledge Chunk

Create an immutable representation for a chunk extracted from a knowledge document.

The chunk should support:

- unique chunk identifier
- parent document identifier
- chunk content
- chunk index/order
- metadata

### 3. Metadata

Metadata must be:

- JSON-compatible
- deterministic
- isolated from caller mutation
- safe for future persistence/indexing

Nested mappings and sequences must not allow accidental mutation of the original caller-owned structures.

### 4. Immutability

Domain objects must be immutable after creation.

Mutation attempts must fail rather than silently changing the model.

### 5. Determinism

Equivalent inputs must produce equivalent identifiers/representations.

Ordering of metadata collections must not depend on object identity or memory addresses.

### 6. Serialization

The domain objects must have a deterministic JSON-compatible representation.

Serialization must not use `str()` or `repr()` as a fallback for arbitrary objects.

### 7. Validation

Reject invalid values such as:

- empty document identifiers
- empty chunk identifiers
- empty content
- negative chunk indexes
- invalid metadata values

### 8. Tests

Add comprehensive tests covering:

- construction
- validation
- immutability
- nested metadata isolation
- deterministic serialization
- deterministic identifiers
- equality
- JSON serialization
- caller mutation isolation

## Compatibility

The implementation must not break:

- Phase 1 analysis models
- Phase 2 AI result models
- existing API contracts
- existing tests

## Scope

Only implement the knowledge-base domain model.

Do not implement:

- embeddings
- vector databases
- ChromaDB
- retrieval
- RAG orchestration
- frontend functionality

## Validation

Run:

pytest
ruff check .
black --check .
python -m mypy app
git diff --check

All must pass before the task is considered complete.

## Completion Criteria

TASK-073 is complete when the knowledge-base domain model is immutable, deterministic, serializable, validated, tested, and ready for use by TASK-074 onward.