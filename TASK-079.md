# TASK-079 — Flow Model

## Phase
PHASE 4 — MODERNIZATION

## Title
Flow Domain Model

## Objective

Introduce the domain model used to represent application execution flows
discovered from legacy mainframe source code.

The model must provide a stable, immutable, deterministic representation of
nodes and relationships in an application flow.

This task defines the data contract only.

Flow generation and analysis belong to later tasks.

---

## Context

The RAG and intelligence phases provide information about:

- source files
- dependencies
- business rules
- analysis results
- knowledge chunks

TASK-079 introduces a normalized flow representation that later tasks can
populate and analyze.

The model must remain independent of:

- visualization
- frontend code
- graph databases
- flow-generation algorithms
- modernization scoring
- recommendation logic

---

## Requirements

### 1. Flow Node

Create an immutable `FlowNode` domain model.

A node represents a meaningful unit in an application flow.

It should support:

- deterministic ID
- node type
- display/name value
- optional source reference
- optional metadata

The node model must validate required fields.

IDs and required textual fields must reject empty or whitespace-only values.

---

### 2. Flow Edge

Create an immutable `FlowEdge` domain model.

An edge represents a directed relationship between two flow nodes.

It should contain:

- deterministic ID
- source node ID
- target node ID
- edge type
- optional metadata

Validation must reject:

- empty IDs
- missing source/target identifiers
- invalid edge definitions

Self-references should be explicitly handled according to the model contract.

---

### 3. Flow Model

Create an immutable `Flow` aggregate.

It should contain:

- flow ID
- name/title
- nodes
- edges
- optional metadata

The aggregate must maintain structural consistency.

Every edge must reference a node contained in the flow.

---

### 4. Node Types

Define an explicit enum for supported node categories.

The initial model should support generic categories required for legacy
application flow representation, such as:

- PROGRAM
- FILE
- DATABASE
- TRANSACTION
- DECISION
- PROCESS
- EXTERNAL

Do not add domain-specific behavior that belongs to later flow-generation
tasks.

---

### 5. Edge Types

Define an explicit enum for supported relationship categories.

At minimum support:

- CALLS
- READS
- WRITES
- FLOWS_TO
- DEPENDS_ON
- INVOKES

The model must remain extensible without requiring changes to the aggregate
structure.

---

### 6. Immutability

All flow models must provide strong immutability.

Mutating:

- original metadata
- node collections
- edge collections
- nested metadata

after construction must not mutate the stored flow.

Returned collections must not expose mutable internal state.

---

### 7. Determinism

Equivalent flow inputs must produce equivalent results.

Ensure deterministic:

- node ordering
- edge ordering
- identifiers
- serialization
- metadata representation

Do not depend on:

- memory addresses
- object identity
- arbitrary set iteration
- `repr()` output

---

### 8. Serialization

Flow models must support JSON-compatible serialization.

Serialized output must contain stable representations of:

- flow
- nodes
- edges
- enums
- metadata

Serialization must not leak implementation details or memory addresses.

---

### 9. Structural Validation

The `Flow` aggregate must validate:

- unique node IDs
- unique edge IDs
- edge source exists
- edge target exists
- valid node types
- valid edge types

Duplicate identifiers must be rejected.

Dangling edges must be rejected.

---

### 10. Caller Isolation

Inputs must be defensively copied.

For example:

```text
caller metadata
      ↓
Flow construction
      ↓
internal immutable metadata