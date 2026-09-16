# TASK-057: Dependency Summary API Integration

## Overview

Task-057 integrates the `DependencyAnalysisSummary` domain model (created in Task-056) into the existing `/analyze` endpoint payload, exposing it as `dependency_summary`. This provides clients with a high-level statistical overview of the dependency resolution for a given COBOL source file, without altering existing response payloads.

## API Integration

The `AnalysisResponse` schema has been extended with an optional field:

```json
{
  "dependency_summary": {
    "node_count": 0,
    "edge_count": 0,
    "resolved_target_count": 0,
    "unresolved_target_count": 0,
    "ambiguous_target_count": 0,
    "dependency_counts": {
      "CALL": 1,
      "PERFORM": 2
    }
  }
}
```

This field uses the new `DependencyAnalysisSummaryResponse` schema. The domain summary is authoritative; the API layer (`analyze_source`) delegates all counting and logic to the underlying `DependencyAnalysisSummary.from_results(...)` model.

### Serialization Details

- **Backward Compatibility**: The existing `AnalysisResponse` fields (`success`, `status`, `ast`, `dependencies`, `diagnostics`, `error`) have been preserved in their entirety. No fields were removed, renamed, or modified in type.
- **Dependency Types**: The `dependency_counts` map uses literal string keys (e.g., `"CALL"`, `"PERFORM"`) instead of enum members, matching the established JSON serialization pattern in the `dependencies` array.

### Semantics

- **Resolved**: The dependency target uniquely matches a COBOL file in the workspace inventory.
- **Unresolved**: The dependency target has no matching file.
- **Ambiguous**: The dependency target matches multiple files.

### Error Handling Behavior

- **Semantic Errors**: If the parser encounters a semantic error but successfully builds an AST, the dependency extraction still executes, and the `dependency_summary` is populated.
- **Internal Errors**: If an internal error prevents AST creation altogether, `dependency_summary` evaluates to `None`.

## Validation

Focused API tests have been added to `tests/analysis/test_api.py` covering:

1. Successful analysis with a dependency summary.
2. Empty dependency graph.
3. Fully resolved dependencies.
4. Mixed resolution states.
5. JSON string serialization of dependency types.
6. Semantic error behaviors (with AST preserved).
7. Internal error behaviors (without AST).