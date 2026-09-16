# TASK-055 — WORKSPACE DEPENDENCY RESOLUTION

## Objective

Resolve dependency-graph targets against the existing workspace inventory.

Task-054 introduced a deterministic, immutable in-memory dependency graph constructed from extracted `Dependency` objects.

Task-055 adds a separate workspace-resolution layer that determines whether graph target identifiers correspond to actual source files in the workspace.

The resolver must use the existing workspace/inventory abstractions.

It must not modify the dependency graph itself.

---

## Background

The current pipeline is:

```text
COBOL Source
    ↓
Lexer
    ↓
Parser
    ↓
AST
    ↓
DependencyAnalyzer
    ↓
Dependency[]
    ↓
DependencyGraph
    ↓
WorkspaceDependencyResolver
    ↓
DependencyResolution[]
```

The resolver bridges the gap between static COBOL dependencies (e.g., `CALL 'SUBPROG'`) and the physical files residing in the uploaded workspace.

---

## Scope

- **`WorkspaceDependencyResolver`**: A service class that consumes a `DependencyGraph` and a `WorkspaceInventory`.
- **`DependencyResolution`**: A typed outcome model encapsulating the original target identifier, the resolution status, and the matched file metadata.
- **`ResolutionStatus`**: Represents the outcome (`RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`).

### Non-Goals

- Do not modify the AST or parser.
- Do not modify `DependencyAnalyzer`.
- Do not modify `DependencyGraph`.
- Do not add COPY or JCL resolution.
- Do not mutate graph objects.
- Do not add graph visualization.
- Do not alter the `/analyze` API endpoint response schema.
- Do not implement RAG/LLM functionality.

---

## Architecture and Semantics

### Resolution Models

The resolution outcomes use the repository's typed conventions:
- `ResolutionStatus` Enum: `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`.
- `DependencyResolution` Dataclass: Records the target string, status, and the matched `ScannedFile`.

### Matching Logic

The matching leverages the existing `WorkspaceInventory` and `ScannedFile` models:
- **Case-Insensitive Exact Match**: Matches against `ScannedFile.filename` (e.g., target `"CUSTOMER.cbl"` matches file `"CUSTOMER.cbl"`).
- **Case-Insensitive Stem Match**: Matches against the basename minus its extension (e.g., target `"CUSTOMER"` matches file `"CUSTOMER.cbl"`).
- **Nested Paths**: Returns the actual `ScannedFile` which transparently carries its absolute/workspace-relative path without flattening directories.
- **Ambiguity**: If a target matches multiple inventory files (e.g., `"CUSTOMER.cbl"` and `"CUSTOMER.cpy"`), it is marked as `AMBIGUOUS`.
- **Determinism**: The graph nodes dictate the deterministic resolution order; duplicate dependencies from multiple edges resolve cleanly as a single target node resolution.