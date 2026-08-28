# TASK-078 — RAG Orchestration

## Phase
Phase 3 — Knowledge / RAG

## Objective

Integrate retrieval with the Phase-2 AI orchestration layer to provide context-aware AI analysis using retrieved knowledge.

## Requirements

### 1. RAG Orchestrator

Create a provider-independent RAG orchestration service.

The flow must be:

    User Query
        ↓
    Query Embedding
        ↓
    Knowledge Retrieval
        ↓
    Context Assembly
        ↓
    AI Orchestration
        ↓
    Normalized AI Result

### 2. Retrieval Integration

Use TASK-077 retrieval results as contextual knowledge.

### 3. Context Assembly

Create a deterministic context representation containing:

- retrieved chunks
- source metadata
- relevance scores
- query information

### 4. Context Limits

Support configurable limits for:

- maximum retrieved chunks
- maximum context size
- maximum individual chunk size

Prevent unbounded context construction.

### 5. AI Integration

Reuse the existing Phase-2 AI orchestration and normalized result contracts.

Do not duplicate explanation/documentation generation logic.

### 6. Provider Independence

The RAG layer must not directly depend on:

- a particular LLM provider
- a particular embedding provider
- ChromaDB APIs

Use abstractions from previous tasks.

### 7. Determinism

Given identical:

- query
- knowledge index
- configuration
- providers

the assembled context and orchestration inputs must be deterministic.

### 8. Failure Handling

Handle independently:

- retrieval failure
- embedding failure
- AI provider failure
- empty retrieval results

Preserve useful information whenever possible.

### 9. Empty Knowledge Base

The system must behave correctly when no relevant knowledge is available.

It must not crash simply because retrieval returns zero results.

### 10. Tests

Cover:

- retrieval-to-AI flow
- context assembly
- deterministic context ordering
- context size limits
- empty retrieval
- retrieval failure
- embedding failure
- AI failure
- provider injection
- immutability
- repeated execution
- normalized result compatibility

### 11. Integration

Verify compatibility with:

- TASK-069 AI orchestration
- TASK-070 AI API
- TASK-071 normalized AI results
- TASK-072 AI result schemas/API

## Scope

Do not implement:

- frontend chat
- production authentication
- deployment
- UI
- production monitoring

Those belong to later phases.

## Validation

pytest
ruff check .
black --check .
python -m mypy app
git diff --check

## Completion Criteria

Phase 3 is complete when knowledge can flow from source/documentation through:

    Knowledge Document
        ↓
    Chunking
        ↓
    Embedding
        ↓
    Indexing
        ↓
    Retrieval
        ↓
    Context Assembly
        ↓
    AI Orchestration
        ↓
    Normalized AI Result