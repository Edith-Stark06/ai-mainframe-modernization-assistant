# TASK-056 — DEPENDENCY ANALYSIS SUMMARY

## Objective

Build a typed, deterministic dependency-analysis summary from the existing:

- `DependencyGraph` from Task-054
- Workspace dependency resolution from Task-055

Task-056 creates a stable domain-level summary that describes the dependency structure and resolution state without modifying the graph or workspace inventory.

---

## Background

The dependency pipeline is now:

```text
COBOL Source
    ↓
Parser
    ↓
DependencyAnalyzer
    ↓
Dependency[]
    ↓
DependencyGraph                 ← Task-054
    ↓
WorkspaceDependencyResolver     ← Task-055
    ↓
Dependency Analysis Summary     ← Task-056
```

---

## Scope

- **`DependencyAnalysisSummary`**: A typed immutable dataclass that computes aggregate properties of the `DependencyGraph` and `DependencyResolution` objects.

### Non-Goals

- Do not modify parser or AST behavior.
- Do not modify `DependencyAnalyzer`.
- Do not modify `DependencyGraph`.
- Do not modify `WorkspaceDependencyResolver`.
- Do not add API endpoints.
- Do not implement JCL/COPYBOOK resolution.

---

## Architecture and Semantics

The summary provides the following aggregated statistics:

- `node_count`: The total number of nodes in the graph (including the root node).
- `edge_count`: The total number of edges in the graph.
- `resolved_target_count`: The number of resolution objects with `ResolutionStatus.RESOLVED`.
- `unresolved_target_count`: The number of resolution objects with `ResolutionStatus.UNRESOLVED`.
- `ambiguous_target_count`: The number of resolution objects with `ResolutionStatus.AMBIGUOUS`.
- `dependency_counts`: A deterministic mapping from `DependencyType` to the number of edges of that type in the graph. It includes no fabricated dependency types (i.e. if the graph has 0 dependencies, this dictionary is empty).

### Matching Logic and Determinism

- The summary uses existing types like `DependencyType` and `ResolutionStatus`.
- The mapping `dependency_counts` is guaranteed to be ordered deterministically (e.g. alphabetically by Enum name) regardless of graph edge order.
- Generating the summary is an inherently read-only operation and strictly mutates no state.