# TASK-050 — Analysis Result Status Contract

## Objective
Introduce an explicit, typed status field (`AnalysisStatus`) to the existing analysis API response to clearly distinguish between successful execution, semantic analysis failures, and internal system errors.

## Current Problem
The API currently returns a boolean `success` field and an optional `error` string. While this identifies if the analysis succeeded, it does not easily differentiate between a semantic error in the user's COBOL code (which is a valid completed analysis) and an unexpected internal server error in the pipeline.

## Exact Status Values and Semantics
- `SUCCESS`: The analysis pipeline completed without internal errors, and the source code has no semantic or compiler-level errors. `AnalysisResult.success` is `True`.
- `ANALYSIS_ERROR`: The analysis pipeline completed normally, but the source code contains semantic or compiler-level errors. `AnalysisResult.success` is `False`, but it is not an internal failure.
- `INTERNAL_ERROR`: The `AnalysisService` encountered an unexpected exception, preventing the pipeline from completing normally.

## Relationship Between Status and Existing Fields
- `success`: Remains for backward compatibility. It is `True` only when `status == SUCCESS`.
- `error`: Remains to contain any exception message if an internal error occurs.
- `diagnostics`: Populated with semantic errors when `status == ANALYSIS_ERROR`.

## API Response Contract
The `AnalysisResponse` model will include:
```python
status: AnalysisStatus = Field(
    ...,
    description="The execution status of the analysis pipeline."
)
```

## Test Requirements
- Successful analysis returns `success == True` and `status == SUCCESS`.
- Semantic-analysis failure returns `success == False` and `status == ANALYSIS_ERROR`.
- `AnalysisService` failure returns `success == False` and `status == INTERNAL_ERROR`.
- JSON response contains the status field.
- Invalid status values are rejected by the response model.
- Existing behaviors (`analysis_id`, `source_metadata`, AST/IR serialization) remain unchanged.
- All existing tests pass.

## Explicit Non-Goals
- **No asynchronous execution**: The endpoint remains fully synchronous.
- **No persistence**: Analysis results will not be stored in a database.
- **No WebSocket/polling API**: Clients will wait for the synchronous HTTP response.
- No new compiler or semantic-analysis features.
- No modifications to the frontend or route path.