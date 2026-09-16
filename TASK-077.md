# TASK-077 — Retrieval Service

## Phase

Phase 3 — Knowledge / RAG

## Objective

Implement a provider-independent retrieval service that accepts a natural-language
query, generates a query embedding, searches the configured vector index, and
returns the most relevant knowledge chunks in deterministic ranked order.

This task introduces retrieval/search behavior.

RAG orchestration, prompt construction, LLM calls, and chat functionality are
explicitly out of scope and belong to TASK-078 and later tasks.

---

## Dependencies

- TASK-073 — Knowledge-base model
- TASK-074 — Code/document chunking
- TASK-075 — Embedding/indexing abstractions
- TASK-076 — ChromaDB ingestion

The implementation must build on the existing abstractions rather than
introducing a second incompatible vector-store or embedding architecture.

---

## Requirements

### 1. Retrieval abstraction

Create a provider-independent retrieval layer.

Suggested location:

    app/rag/retrieval/

The retrieval service must not directly depend on ChromaDB.

ChromaDB-specific behavior must remain behind the existing `VectorIndex`
abstraction.

---

### 2. Query embedding

The retrieval service must accept a text query and generate its embedding using
the existing `EmbeddingProvider` abstraction.

Do not introduce a second embedding provider interface.

The query embedding must use the same dimensionality expectations as the
configured vector index.

---

### 3. Vector search

Extend the vector-index abstraction only as necessary to support retrieval.

The retrieval operation must support:

- query vector
- top-k limit
- optional supported metadata filter
- ranked results
- similarity/distance information where appropriate

The concrete ChromaDB implementation from TASK-076 may implement the required
search operation behind the abstraction.

Do not expose ChromaDB-specific result types outside the indexing layer.

---

### 4. Retrieval result

Define a stable retrieval result representation.

A result should preserve enough information for later RAG processing, including:

- knowledge chunk ID
- document ID
- chunk content
- chunk index
- metadata
- similarity/distance score where applicable

The result representation must be immutable or otherwise protected from caller
mutation.

---

### 5. Top-k

Support a configurable `top_k`.

Validation requirements:

- `top_k` must be an integer
- `top_k` must be greater than zero
- unreasonable/unbounded values must be rejected according to the service's
  configured limits

The service must never silently return more than the requested number of
results.

---

### 6. Ranking

Results must be ordered from most relevant to least relevant.

The implementation must clearly define whether the underlying index returns
similarity or distance and normalize the interpretation consistently.

Do not assume that a larger value is always better without checking the index
semantics.

---

### 7. Deterministic tie-breaking

When two or more results have equal relevance, ordering must be deterministic.

Use a stable secondary key such as:

1. score/distance
2. document ID
3. chunk index
4. chunk ID

The exact ordering must be documented and tested.

Repeated identical queries against identical indexed data must produce identical
ordering.

---

### 8. Empty results

A query with no matching chunks must return an empty result collection.

It must not:

- raise an unexpected exception
- return fabricated content
- return `None` when an empty collection is appropriate

---

### 9. Query validation

Reject invalid queries clearly.

At minimum:

- empty string
- whitespace-only query

The service should preserve the original meaningful query text rather than
silently modifying it in a way that changes semantics.

---

### 10. Metadata filtering

If metadata filtering is supported by the existing index abstraction, expose
it through the retrieval service using a provider-independent representation.

Do not expose ChromaDB's filter syntax directly to callers.

Filtering must be deterministic and must not mutate stored metadata.

---

### 11. Error handling

Define clear behavior for:

- embedding-provider failures
- index failures
- invalid query
- invalid top-k
- invalid filters
- dimension mismatch

Errors must not be silently swallowed.

Do not fabricate fallback retrieval results.

---

### 12. Immutability

Retrieval must never mutate:

- stored `KnowledgeDocument`
- stored `KnowledgeChunk`
- stored `Embedding`
- caller-provided metadata
- caller-provided filters

Returned results must not provide a mutation path back into stored data.

---

### 13. Determinism

For identical:

- query
- embeddings
- index contents
- configuration

the retrieval service must return the same ordered results.

Avoid nondeterministic ordering from sets, dictionary iteration, or backend
result ordering.

---

## Testing Requirements

Add tests under:

    tests/rag/

Cover at minimum:

### Basic retrieval

- retrieve one matching chunk
- retrieve multiple matching chunks
- retrieve results from multiple documents

### Top-k

- `top_k=1`
- `top_k` greater than available results
- invalid zero
- invalid negative value
- invalid non-integer value

### Ranking

- most relevant result appears first
- distance/similarity semantics are correct
- score information is preserved if required

### Determinism

- repeated identical query returns identical ordering
- equal-score results use deterministic tie-breaking
- backend result ordering does not affect final ordering

### Query validation

- empty query rejected
- whitespace-only query rejected

### Empty retrieval

- no matches returns an empty collection

### Metadata

- metadata is preserved
- metadata filtering works if supported
- unsupported filters are rejected clearly

### Error handling

- embedding provider failure
- index failure
- embedding dimension mismatch
- invalid retrieval parameters

### Immutability

Verify that retrieval does not mutate:

- indexed chunks
- source metadata
- query input
- filters

Verify that callers cannot mutate returned data and thereby modify indexed
state.

### Compatibility

All tests from TASK-073 through TASK-076 must continue to pass.

---

## ChromaDB Integration

Use the TASK-076 ChromaDB implementation through the vector-index abstraction.

Do not bypass the abstraction by importing ChromaDB directly into the retrieval
service.

Integration tests may use local persistent ChromaDB with temporary directories.

No external ChromaDB server may be required.

---

## Explicitly Out of Scope

Do NOT implement:

- RAG prompt construction
- LLM calls
- context-window management
- answer generation
- conversational memory
- chat API
- frontend functionality
- modernization recommendations
- reranking using an LLM
- TASK-078 orchestration

---

## Quality Requirements

The implementation must provide:

- provider independence
- vector-store independence
- deterministic ranking
- deterministic tie-breaking
- immutable results
- caller isolation
- explicit validation
- clear errors
- JSON-safe result data where applicable
- no hidden global state

Run:

    pytest tests/rag -q
    pytest tests/ai -q
    pytest tests/analysis/rules -q
    pytest tests/analysis/dependencies -q
    pytest tests/analysis -q
    pytest tests/integration -q
    pytest -q

Also run:

    ruff check .
    black --check .
    python -m mypy app
    git diff --check

---

## Scope

Only modify files required for TASK-077.

Do not modify unrelated parser/IR behavior.

Do not prematurely implement TASK-078.

Do not introduce frontend or API changes unless explicitly required by this
task specification.

---

## Completion Criteria

TASK-077 is complete when:

1. A provider-independent retrieval service exists.
2. Queries are embedded using the existing embedding abstraction.
3. Vector search is exposed through the index abstraction.
4. Results are ranked correctly.
5. `top_k` is enforced.
6. Equal-score results have deterministic ordering.
7. Empty retrieval returns an empty collection.
8. Invalid queries and parameters are rejected.
9. Metadata is preserved and filtering works where supported.
10. Provider/index failures are surfaced clearly.
11. Returned results are immutable and isolated from stored state.
12. Retrieval is deterministic.
13. ChromaDB remains an infrastructure detail.
14. TASK-073 through TASK-076 remain compatible.
15. All required tests and static checks pass.
16. Changes are committed and pushed.
17. A GitHub PR is created against `main`.
18. The final report includes the commit SHA, branch, PR URL/state,
    test results, static-check results, and any baseline failures.

---

## Final Decision Rule

Report:

    READY FOR REVIEW

only when the TASK-077 implementation and required validation checks actually
pass.

If unrelated baseline failures exist, identify them explicitly and do not claim
they were caused by TASK-077 without evidence.