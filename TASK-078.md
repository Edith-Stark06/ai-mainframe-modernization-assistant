# TASK-078 — RAG Orchestration

## Phase
PHASE 3 — KNOWLEDGE / RAG

## Title
RAG Orchestration

## Objective

Implement the RAG orchestration layer that combines:

1. Query embedding
2. Knowledge-base retrieval
3. Retrieved context construction
4. Context-aware AI generation

The orchestration layer must coordinate the existing RAG components without
duplicating their responsibilities.

---

## Existing Components

The implementation must build on the existing architecture:

- `KnowledgeDocument`
- `KnowledgeChunk`
- `Embedding`
- `EmbeddingProvider`
- `EmbeddingService`
- `VectorIndex`
- `InMemoryIndex`
- `ChromaIndex`
- `RetrievalResult`
- `RetrievalService`
- Existing AI orchestration/provider abstractions

Do not replace or bypass these components.

---

## Requirements

### 1. RAG Request Model

Create an immutable request model representing a RAG query.

Required information should include:

- query text
- `top_k`
- optional metadata filters
- optional AI capability/request information

Validation must reject:

- empty queries
- whitespace-only queries
- invalid `top_k`
- invalid metadata filters

---

### 2. Retrieved Context Model

Create an immutable model representing the context supplied to the AI layer.

It should preserve:

- retrieved chunk IDs
- document IDs
- chunk content
- ranking/distance information
- relevant metadata

The context must:

- preserve deterministic ordering
- isolate callers from internal state
- remain JSON serializable
- prevent accidental mutation

---

### 3. RAG Result Model

Create a stable result model containing:

- original query
- retrieved results/context
- optional AI analysis/result
- deterministic metadata

The result must distinguish between:

- retrieval-only success
- retrieval + AI success
- retrieval success with AI unavailable/failure

Do not silently discard retrieval results when AI generation fails.

---

### 4. RAG Orchestrator

Implement a `RAGOrchestrator` responsible for coordinating:

```text
User Query
    ↓
Query Validation
    ↓
Embedding / Retrieval
    ↓
Ranked Knowledge Context
    ↓
AI Orchestration
    ↓
RAG Result