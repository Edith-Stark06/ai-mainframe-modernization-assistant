# TASK-058: Dependency Graph API Representation

## Objective

Task-058 exposes the `DependencyGraph` domain model through the existing `/analyze` endpoint payload, exposing it as `dependency_graph`. This allows API consumers to inspect the full structure of dependencies for a COBOL program (nodes, edges, dependency types, and source locations).

## API Integration

The `AnalysisResponse` schema has been extended with an optional field:

```json
{
  "dependency_graph": {
    "nodes": [
      {
        "identifier": "HELLO-WORLD"
      }
    ],
    "edges": [
      {
        "source": "HELLO-WORLD",
        "target": "CUSTOMER-SERVICE",
        "dependency_type": "CALL",
        "source_location": {
          "type": "Position",
          "line": 6,
          "column": 13,
          "offset": 42,
          "filename": "hello.cbl"
        }
      }
    ]
  }
}
```

### Serialization Details

- **Authoritative Source**: The existing domain `DependencyGraph` is the authoritative source. The API layer serializes it directly without reconstructing it from raw dependencies or summary counts.
- **Dependency Types**: The `dependency_type` string (e.g., `"CALL"`, `"PERFORM"`) is preserved as a literal string.
- **Source Locations**: The `source_location` uses the existing `PositionResponse` schema contract.
- **Deterministic Ordering**: Nodes and edges are returned as lists exactly matching their order in the domain graph's tuples. Sorting or deduplication is handled by the domain graph abstraction, preserving accuracy.
- **Backward Compatibility**: The existing fields (`success`, `status`, `ast`, `dependencies`, `dependency_summary`, `diagnostics`, `error`) have been preserved in their entirety. No fields were removed.

### Error Handling Behavior

- **Semantic Errors**: If the parser encounters a semantic error but successfully builds an AST, the dependency graph will still be populated with any extracted nodes and edges.
- **Internal Errors**: If an internal error prevents AST creation altogether, `dependency_graph` evaluates to `None`. No fabricated empty graph is emitted.

## Validation

Focused API tests have been added to `tests/analysis/test_api.py` covering:

1. Empty graph serialization.
2. CALL edges.
3. PERFORM edges.
4. Same targets with multiple CALL + PERFORM occurrences (deterministic ordering and duplicate edge preservation).
5. Source location serialization matching the existing `PositionResponse` contract.
6. Semantic error behaviors (with AST and graph preserved).
7. Internal error behaviors (without AST or graph).