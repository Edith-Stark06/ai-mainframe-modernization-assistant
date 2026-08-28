# TASK-074 — Code / Document Chunking

## Phase
Phase 3 — Knowledge / RAG

## Objective

Implement deterministic chunking of analyzed source code and documentation into KnowledgeChunk objects suitable for embedding and indexing.

## Requirements

### 1. Chunking Service

Create a provider-independent chunking service.

The service must accept supported knowledge sources and produce KnowledgeChunk objects.

### 2. Supported Sources

Support:

- source code
- generated documentation
- analysis/documentation text
- structured knowledge documents

### 3. Deterministic Chunking

Identical input must always produce:

- identical chunk boundaries
- identical chunk ordering
- identical chunk identifiers

### 4. Chunk Size

Provide configurable:

- maximum chunk size
- overlap
- minimum chunk size

Configuration must have sensible defaults.

### 5. Context Preservation

Chunks must retain sufficient metadata to identify:

- source document
- source file
- chunk position
- content type
- relevant analysis context

### 6. Code Awareness

Where possible, avoid arbitrarily splitting structured source code.

Prefer logical boundaries such as:

- paragraphs
- declarations
- procedures
- sections
- documentation sections

### 7. Immutability

Returned chunks must not expose mutable caller-owned state.

### 8. Tests

Cover:

- empty input
- small input
- large input
- exact boundary
- overlap
- deterministic ordering
- deterministic IDs
- source metadata
- code chunking
- documentation chunking
- repeated execution
- caller mutation

## Scope

Do not implement:

- embeddings
- vector storage
- retrieval
- RAG prompting

## Validation

pytest
ruff check .
black --check .
python -m mypy app
git diff --check