# TASK-076 — ChromaDB Ingestion

## Phase

Phase 3 — Knowledge / RAG

## Objective

Integrate ChromaDB as a persistent vector-store backend and implement
deterministic ingestion of knowledge chunks and their embeddings.

This task introduces persistence only.

Retrieval, similarity search, ranking, and RAG orchestration are explicitly
out of scope and belong to TASK-077 and TASK-078.

---

## Dependencies

- TASK-073 — Knowledge-base model
- TASK-074 — Code/document chunking
- TASK-075 — Embedding/indexing abstractions

The implementation must use the existing `KnowledgeChunk`, `Embedding`,
`EmbeddingProvider`, `EmbeddingService`, and `VectorIndex` abstractions where
appropriate.

---

## Requirements

### 1. ChromaDB dependency

Add ChromaDB as a project dependency.

The integration must be isolated behind the application's indexing layer.

Application/domain code must not depend directly on ChromaDB-specific types.

---

### 2. ChromaDB index implementation

Implement a ChromaDB-backed `VectorIndex`.

Suggested location:

    app/rag/indexing/chroma.py

The implementation must satisfy the existing `VectorIndex` abstraction from
TASK-075.

It must support:

- creating/opening a collection
- adding embeddings
- deterministic IDs
- storing chunk metadata
- persistent local storage
- collection isolation
- dimension validation
- deterministic ingestion

---

### 3. Persistent storage

The ChromaDB index must support a configurable persistence directory.

Do not hard-code an absolute filesystem path.

The persistence location must be supplied through configuration or an explicit
constructor argument.

Two index instances pointing to the same persistence location and collection
must observe the same stored data.

---

### 4. Collection isolation

Different collections must not interfere with one another.

For example:

    collection_a
    collection_b

must maintain independent records even when they share the same persistence
directory.

Collection names must be validated before use.

---

### 5. Ingestion

Implement ingestion of the existing embedding representation into ChromaDB.

Each indexed item must preserve:

- embedding ID
- vector
- knowledge chunk identity
- document identity
- chunk index
- supported metadata

The implementation must not mutate the original `Embedding` or
`KnowledgeChunk` objects.

---

### 6. Deterministic IDs

The same logical chunk must produce the same stored identifier.

Repeated ingestion of the same logical data must not create duplicate
records.

The implementation must define deterministic behavior for duplicate IDs.

Prefer idempotent upsert semantics where supported.

---

### 7. Metadata

Only JSON-compatible metadata may be persisted.

Metadata must preserve the normalized values produced by TASK-073.

Unsupported metadata must be rejected clearly rather than silently converted
using `str()` or `repr()`.

Metadata ordering must not affect deterministic behavior.

---

### 8. Embedding validation

Before persistence, validate:

- embedding dimension
- vector length
- finite numeric values
- non-empty identifier
- valid metadata

Invalid embeddings must produce clear domain/application errors.

---

### 9. Persistence behavior

The implementation must prove that data survives recreation of the index
object.

Example:

    index_1 = ChromaIndex(path, "knowledge")
    index_1.add(...)

    index_2 = ChromaIndex(path, "knowledge")
    index_2.get(...)

The second instance must observe the previously ingested data.

---

### 10. Offline testability

Tests must not depend on an external ChromaDB server.

Use ChromaDB's local/persistent client mode.

Tests must use temporary directories.

Tests must clean up temporary resources automatically.

---

## Explicitly Out of Scope

Do NOT implement:

- similarity search
- nearest-neighbor retrieval
- ranking
- reranking
- retrieval service
- query embedding
- RAG prompts
- LLM calls
- RAG orchestration
- chat functionality
- frontend changes

These belong to later tasks.

---

## Testing Requirements

Add tests covering at minimum:

### Basic ingestion

- create collection
- add one embedding
- add multiple embeddings
- retrieve stored records by ID for verification

### Persistence

- write using one index instance
- recreate the index
- verify the records remain available

### Collection isolation

- two collections
- same persistence directory
- verify records remain isolated

### Determinism

- same input produces same ID
- repeated ingestion is idempotent
- metadata ordering does not change behavior

### Validation

- empty IDs rejected
- invalid dimensions rejected
- mismatched vector dimensions rejected
- non-finite vectors rejected
- unsupported metadata rejected

### Immutability

Verify that:

- source `KnowledgeChunk` is unchanged
- source `Embedding` is unchanged
- caller-owned metadata is not mutated

### JSON compatibility

Verify persisted metadata can be represented safely as JSON-compatible
values.

### Compatibility

All existing TASK-073, TASK-074, and TASK-075 tests must continue to pass.

---

## Quality Requirements

The implementation must satisfy:

- deterministic behavior
- provider independence
- domain isolation from ChromaDB
- persistent local storage
- caller isolation
- immutable source objects
- explicit validation
- clear error handling
- JSON-safe metadata
- no hidden global state

Run:

    pytest
    ruff check .
    black --check .
    python -m mypy app
    git diff --check

---

## Scope

Only modify files required for TASK-076.

Do not modify retrieval or RAG orchestration code.

Do not prematurely implement TASK-077 or TASK-078.

---

## Completion Criteria

TASK-076 is complete when:

1. ChromaDB is integrated as a `VectorIndex` implementation.
2. Knowledge embeddings can be persisted locally.
3. Persistence survives index recreation.
4. Collections are isolated.
5. Ingestion is deterministic and idempotent.
6. Metadata is validated and JSON-safe.
7. Source objects remain immutable.
8. Tests cover persistence and failure cases.
9. Existing tests remain compatible.
10. pytest, ruff, black, mypy, and git diff checks pass.
11. Changes are committed and pushed.
12. A GitHub PR is created against `main`.