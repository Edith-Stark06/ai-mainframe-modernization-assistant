# TASK-076 — ChromaDB Ingestion

## Phase
Phase 3 — Knowledge / RAG

## Objective

Implement ingestion of KnowledgeChunk objects and their embeddings into ChromaDB through the indexing abstraction.

## Requirements

### 1. ChromaDB Adapter

Create an adapter implementing the project indexing abstraction.

The rest of the application must not depend directly on ChromaDB APIs.

### 2. Collection Management

Support:

- collection creation
- collection lookup
- collection initialization
- collection configuration

### 3. Ingestion

Ingest:

- chunk IDs
- chunk documents
- embeddings
- metadata

### 4. Upsert

Repeated ingestion of the same chunk must not create duplicate records.

Use stable chunk identifiers.

### 5. Batch Processing

Support ingestion in batches.

Batch size must be configurable.

### 6. Metadata

Persist enough metadata to reconstruct retrieval context, including:

- document ID
- source
- chunk index
- content type
- original metadata

### 7. Error Handling

Handle:

- unavailable ChromaDB
- malformed embeddings
- duplicate identifiers
- invalid metadata
- collection failures

Errors must be explicit and actionable.

### 8. Offline Testing

Tests must not require a running external ChromaDB server.

Use an in-memory/local test configuration where possible.

### 9. Tests

Cover:

- collection initialization
- ingestion
- batch ingestion
- repeated ingestion
- upsert
- metadata persistence
- error handling
- empty ingestion
- deterministic IDs
- isolation between collections

## Scope

Do not implement retrieval ranking or RAG orchestration.

Those belong to TASK-077 and TASK-078.

## Validation

pytest
ruff check .
black --check .
python -m mypy app
git diff --check