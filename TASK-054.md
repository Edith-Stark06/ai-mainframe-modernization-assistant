# TASK-054 — DEPENDENCY GRAPH FOUNDATION

## Objective
Build a deterministic, typed, in-memory dependency graph from the existing dependency information produced by Task-051 and exposed through Task-052/Task-053.

Task-054 is the first graph-layer foundation. It operates only on already extracted `Dependency` objects.

## Scope
- Create typed, immutable graph domain models: `DependencyGraphNode`, `DependencyGraphEdge`, `DependencyGraph`.
- Provide deterministic graph construction from `source: str` and `list[Dependency]`.
- Preserve source locations, CALL/PERFORM types, and deterministic ordering.
- Handle duplicate edges deterministically.
- Add comprehensive graph unit tests.

## Non-Goals
- No parser, lexer, AST, or `DependencyAnalyzer` modifications.
- No changes to `Dependency` model or `DependencyType` enum.
- No filesystem resolution, workspace discovery, or JCL analysis.
- No COPY support.
- No dependency graph resolution or cross-file analysis.
- No new API endpoint or API integration.
- No graph visualization or frontend changes.
- No RAG, LLM, or modernization scoring changes.

## Architecture
- **Dependency Flow**: COBOL Source -> Lexer -> Parser -> AST -> `DependencyAnalyzer` -> `Dependency[]` -> `DependencyGraph`.
- **`DependencyGraphNode`**: Immutable node keyed by `identifier: str`.
- **`DependencyGraphEdge`**: Immutable directed edge with `source`, `target`, `dependency_type` (reuses `DependencyType`), and `source_location` (reuses `Position`).
- **`DependencyGraph`**: Immutable container with `nodes: tuple[...]` and `edges: tuple[...]`.
- **Construction**: `DependencyGraph.from_dependencies(source, dependencies)` builds the graph deterministically.
- **Source Node**: Always created as the first node.
- **Target Nodes**: Created from every unique dependency target.
- **Edge Direction**: Always `source → target`.
- **Duplicate Edges**: Omitted; first occurrence preserved.
- **Ordering**: Input order preserved for both nodes and edges.
- **Empty Graph**: Contains one source node and zero edges.

## Validation
- `pytest tests/analysis/dependencies -q` — graph and analyzer tests pass.
- `pytest tests/analysis -q` — analysis suite passes.
- `pytest tests/integration -q` — integration suite passes.
- `pytest -q` — full suite passes (only pre-existing baseline failures remain).
- `ruff check .` — no new violations.
- `black --check .` — formatting clean.
- `python -m mypy app` — type checks pass.
- `git diff --check` — no whitespace errors.
