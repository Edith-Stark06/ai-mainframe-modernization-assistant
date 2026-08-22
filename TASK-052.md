# TASK-052 — ANALYSIS DEPENDENCY CONTRACT

## Objective
Integrate the existing `DependencyAnalyzer` (from Task-051) into the core `AnalysisService` pipeline, exposing the extracted COBOL dependencies through the existing workspace analysis API response (`AnalysisResponse`).

## Scope
- Execute the dependency extraction phase strictly after parsing and before semantic analysis, reusing the same AST.
- Attach a typed `dependencies: list[Dependency]` to `AnalysisResult`.
- Safely serialize the results using existing dataclass/enum serialization primitives.
- Expose the dependencies explicitly in `AnalysisResponse` under the field `dependencies`.
- Provide zero-violation regression tests for all APIs and pipelines impacted.

## Non-Goals
- No parser/lexer modifications.
- No semantic logic enhancements for COPY implementations.
- No distinct "dependency" endpoint creation.
- No resolution or dependency graph logic.
- No frontend/UI/LLM features.

## Architecture
- **Dependency Flow**: COBOL Source -> Lexer -> Parser -> AST -> `DependencyAnalyzer` -> Semantic Analysis -> IR -> Java Backend -> `AnalysisResult` -> JSON Response.
- **`AnalysisResult` Change**: Added `dependencies: list[Dependency]`.
- **API Response Change**: Added `dependencies: list[dict[str, Any]] = Field(default_factory=list)`.
- **Serialization**: `DependencyType.CALL` correctly resolves to `"CALL"`, and `source_location` resolves via the deterministic dataclass serializers.
- **Empty Behavior**: Returns `[]` effectively when no dependencies are found, or when analysis bails out early (e.g. invalid syntax error).
- **Source Locations**: Preserved perfectly from `Task-051` logic as typed `Position` representations.
- **COPY Limitation**: Preserved - `COPY` statements continue to not be explicitly fabricated as the parser omits them from the AST.

## Validation
- Ran full focused dependency suite: `pytest tests/analysis/dependencies -q`.
- Ran core analysis suite: `pytest tests/analysis -q`.
- Verified typing, formatting and linting: `mypy`, `black`, `ruff`.
- `AnalysisService` verifies accurate injection inside internal execution flow.
- `AnalysisResponse` validation affirms correct JSON structures via schema.