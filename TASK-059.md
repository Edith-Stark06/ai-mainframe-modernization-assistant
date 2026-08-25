# TASK-059: DEPENDENCY GRAPH API HARDENING

## Objective
The objective of this task is to harden the existing `dependency_graph` API contract, enforcing strict validation boundaries while remaining fully aligned with the established domain semantics. No changes were made to the core DependencyGraph representation; the focus is exclusively on standardizing and strictly validating the API representation.

## Graph Contract
The serialized graph strictly models nodes and edges:
- `nodes` represents a flat list of dependency nodes. 
- `edges` represents a list of dependencies between programs.

### Validation Behavior
- **Node Identifier**: Node identifiers (`identifier`) are strictly enforced as strings with `min_length=1`.
- **Edge Serialization**:
  - `dependency_type` is validated as a `Literal["CALL", "PERFORM"]`, rejecting python enums and invalid structures.
  - `source_location` precisely reuses `PositionResponse` and preserves original offset, row, col without generating alternative formats.
- **Edge Consistency**: Edge relationships are structurally validated through a `model_validator` in `DependencyGraphResponse`. The Pydantic validator guarantees that for every edge `source -> target`, both the `source` and `target` accurately resolve to existing items contained in the serialized `nodes` list.

## Error Behavior
- **Semantic Error**: When source semantics trigger a compiler diagnostic but AST parsing completes, the API preserves dependency graph visibility (behaving identically to previous behaviors).
- **Internal Error**: In the event of an internal compiler crash where AST construction aborts, the API natively sets `dependency_graph = None`. We explicitly do NOT fabricate an empty graph in this scenario.

## Serialization & Backward Compatibility
- **Duplicates & Structure**: Graph semantics preserve exact representations modeled by the underlying `DependencyGraph`. Deduplication or arbitrary sorting have not been superimposed.
- **Empty Graph Support**: In instances where valid parsings yield no dependencies, the serialization supports explicit rendering of empty lists (`{"nodes": [], "edges": []}`).
- **Fields Preserved**: `success`, `status`, `ast`, `ir`, `diagnostics`, `dependencies`, `dependency_summary`, `dependency_graph`, and `error` structures have been preserved without degradation.

## Test Coverage
Focused tests were deployed extending validation over:
- Valid non-empty schemas
- Valid empty graph schemas 
- CALL edge serialization 
- PERFORM edge serialization 
- Precise validation for `source_location`
- Edges resolving uniquely against strictly known existing nodes 
- Immediate runtime rejection of invalid/dangling edges
- Deterministic enum string resolution for serialization
- Correct propagation under `semantic-error` behaviors
- Correct `None` assignment on `internal-error` triggers
- Overall backward field continuity