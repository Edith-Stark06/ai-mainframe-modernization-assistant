# TASK-075 — Embedding / Indexing

## Phase

Phase 3 — Knowledge / RAG

## Objective

Introduce the embedding and indexing abstraction required to transform
`KnowledgeChunk` objects into searchable vector representations.

Task-075 must establish provider-independent embedding and index contracts
without coupling the implementation to ChromaDB.

## Scope

Implement:

- embedding provider abstraction
- deterministic/offline embedding implementation for tests
- embedding result/domain model
- vector/index abstraction
- chunk-to-embedding workflow
- validation and deterministic behavior
- comprehensive tests

Do NOT implement:

- ChromaDB
- persistent vector database storage
- retrieval/ranking
- RAG orchestration
- API endpoints
- frontend changes

Those belong to later tasks.

---

## Existing Inputs

Task-073 provides:

- `KnowledgeDocument`
- `KnowledgeChunk`
- immutable metadata
- deterministic chunk identifiers

Task-074 provides:

- deterministic document chunking
- `KnowledgeChunk` instances with chunk metadata
- `chunk_index`
- source boundaries
- deterministic chunk content

Task-075 consumes these objects without modifying their contracts.

---

## 1. Embedding Domain Model

Create an immutable embedding representation.

Suggested location:

    app/rag/embeddings/models.py

The model should represent:

- source chunk ID
- embedding vector
- embedding dimension
- optional model/provider identifier

Requirements:

- immutable
- structurally comparable
- deterministic serialization
- JSON-compatible serialization
- reject invalid dimensions
- reject empty vectors
- reject non-numeric vector values
- reject NaN/infinite values
- preserve vector ordering

Example conceptual representation:

    Embedding(
        chunk_id="...",
        vector=(0.1, 0.2, ...),
        dimension=384,
        model="..."
    )

The exact model name/dimension must remain configurable.

---

## 2. Embedding Provider Abstraction

Create a provider-independent interface.

Suggested location:

    app/rag/embeddings/provider.py

The abstraction must support:

    embed(text)
    embed_batch(texts)

The interface must:

- accept text
- return deterministic `Embedding`-compatible vectors
- support batch processing
- validate inputs
- preserve input ordering
- avoid provider-specific dependencies

Do not hard-code OpenAI, HuggingFace, SentenceTransformers,
or another external provider into the domain contract.

---

## 3. Deterministic Test Provider

Create a deterministic local implementation for tests.

It must:

- require no network
- require no API key
- produce the same vector for identical text
- produce stable results across repeated runs
- preserve batch ordering
- produce vectors with a fixed configured dimension

Do not use:

- Python's randomized `hash()`
- object identity
- timestamps
- random UUIDs
- memory addresses
- `repr()` as an embedding source

A cryptographic digest such as SHA-256 may be used as deterministic input
to the vector generation.

---

## 4. Batch Embedding

Provide a service that converts:

    list[KnowledgeChunk]

into:

    list[Embedding]

Requirements:

- preserve chunk ordering
- preserve chunk IDs
- produce exactly one embedding per input chunk
- reject duplicate chunk IDs where uniqueness is required
- reject empty input only if the contract explicitly requires it;
  otherwise return an empty result deterministically
- avoid mutating the original chunks

Suggested location:

    app/rag/embeddings/service.py

---

## 5. Index Abstraction

Create a provider-independent vector index contract.

Suggested location:

    app/rag/indexing/

The index abstraction should support the minimum operations needed by
future retrieval:

- add/upsert embeddings
- check whether a chunk is indexed
- retrieve stored embedding by chunk ID
- report index size

Do not implement similarity retrieval yet unless it is strictly required
by the existing task specification.

Do not introduce ChromaDB.

The index should be replaceable by a future ChromaDB implementation.

---

## 6. In-Memory Index

Provide an in-memory implementation for deterministic tests.

Requirements:

- no external services
- deterministic
- preserves chunk ID → embedding association
- duplicate IDs must have clearly defined behavior
- dimension mismatches must be rejected
- invalid embeddings must be rejected
- caller-owned mutable structures must not be retained directly

The implementation must be safe from accidental mutation through
returned collections.

---

## 7. Determinism

Identical input must produce identical output.

Verify:

    embed(text) == embed(text)

across repeated invocations.

Verify:

    embed_batch([A, B, C])

always returns:

    [embedding(A), embedding(B), embedding(C)]

Do not depend on unordered dictionary/set iteration.

---

## 8. Immutability / Isolation

Embedding vectors must not be mutable through external references.

For example:

    original = [...]
    embedding = ...

Mutating `original` must not mutate the embedding.

Likewise, callers must not be able to mutate an embedding through the
returned vector.

The index must isolate stored values from caller mutation.

---

## 9. Serialization

Embedding objects must support deterministic JSON-compatible serialization.

Verify:

    json.dumps(embedding.to_dict())

succeeds.

Serialization must not contain:

- memory addresses
- object repr strings
- provider-specific runtime objects
- non-JSON numeric values

---

## 10. Validation

Cover at minimum:

- empty text
- whitespace-only text
- invalid vector dimension
- empty vector
- dimension/vector-length mismatch
- non-numeric vector values
- NaN
- infinity
- duplicate chunk IDs
- index dimension mismatch
- invalid chunk IDs
- batch ordering

Use explicit, meaningful exceptions.

---

## 11. Tests

Create:

    tests/rag/test_embeddings.py
    tests/rag/test_indexing.py

Required coverage:

### Embedding model

- valid embedding
- empty vector rejection
- dimension validation
- non-numeric rejection
- NaN/infinity rejection
- immutability
- equality
- deterministic serialization

### Provider

- deterministic single embedding
- deterministic repeated embedding
- batch embedding
- batch ordering
- empty input behavior
- invalid text behavior

### Embedding service

- chunk → embedding conversion
- one-to-one mapping
- chunk ID preservation
- ordering
- duplicate ID validation
- source immutability

### Index

- insert/upsert
- lookup
- contains
- size
- duplicate behavior
- dimension validation
- immutability
- caller isolation
- deterministic behavior

### Integration

Verify:

    KnowledgeChunk
        ↓
    EmbeddingService
        ↓
    Embedding
        ↓
    InMemoryIndex

works end-to-end.

---

## 12. Compatibility

Do not modify:

- Task-073 knowledge model semantics
- Task-074 chunking behavior
- Task-069 orchestration
- Task-070 API
- Task-071 normalized AI results
- Task-072 AI result schemas

Task-075 must be additive.

---

## 13. Scope

Expected additions are limited to the RAG embedding/indexing layer and
its tests.

Do not add:

- ChromaDB dependencies
- retrieval services
- RAG orchestration
- API routes
- UI
- production cloud embedding configuration

---

## 14. Validation Commands

Run:

    pytest tests/rag -q
    pytest tests/ai -q
    pytest tests/analysis/rules -q
    pytest tests/analysis/dependencies -q
    pytest tests/analysis -q
    pytest tests/integration -q
    pytest -q

Then:

    ruff check .
    black --check .
    python -m mypy app
    git diff --check

---

## 15. Git

Branch:

    feat/task-075-embedding-indexing

Commit:

    feat: Task-075 embedding and indexing abstractions

Create one PR against `main`.

Do not merge the PR.

---

## 16. Final Report

Return:

TASK-075 FINAL REPORT

Embedding model:
PASS/FAIL

Provider abstraction:
PASS/FAIL

Deterministic provider:
PASS/FAIL

Batch embedding:
PASS/FAIL

Embedding service:
PASS/FAIL

Index abstraction:
PASS/FAIL

In-memory index:
PASS/FAIL

Dimension validation:
PASS/FAIL

Determinism:
PASS/FAIL

Immutability:
PASS/FAIL

Caller isolation:
PASS/FAIL

Serialization:
PASS/FAIL

Task-073 compatibility:
PASS/FAIL

Task-074 compatibility:
PASS/FAIL

Tests:
PASS/FAIL

Full pytest:
PASS/FAIL

ruff:
PASS/FAIL

black:
PASS/FAIL

mypy:
PASS/FAIL

git diff --check:
PASS/FAIL

Scope:
PASS/FAIL

Commit:
<actual SHA>

PR:
<actual PR number and URL>

State:
OPEN

Merged:
false

Final decision:

READY FOR REVIEW

Only report READY FOR REVIEW when all required checks pass.

DO NOT MERGE.