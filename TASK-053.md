# TASK-053 — DEPENDENCY API SCHEMA HARDENING

## Objective
Harden the dependency contract exposed by the workspace analysis API by replacing the generic dependency representation with a dedicated typed API schema, while preserving the existing JSON contract introduced by Task-052.

## Scope
- Introduce a typed `DependencyResponse` API schema for serialized COBOL dependencies.
- Introduce a typed `PositionResponse` API schema for serialized source positions.
- Update `AnalysisResponse.dependencies` from `list[dict[str, Any]]` to `list[DependencyResponse]`.
- Preserve the exact Task-052 JSON contract (types, targets, source locations, ordering, deduplication).
- Strengthen CALL/PERFORM API validation with real COBOL integration tests.
- Validate the API response through the actual `AnalysisResponse` and `DependencyResponse` models.

## Non-Goals
- No parser, lexer, AST, or `DependencyAnalyzer` modifications.
- No changes to the `Dependency` model or `DependencyType` enum.
- No COPY handling changes.
- No dependency graph or resolution logic.
- No new dependency endpoint.
- No frontend, RAG, LLM, JCL, or modernization scoring changes.

## Architecture
- **Dependency Flow**: COBOL Source -> Lexer -> Parser -> AST -> `DependencyAnalyzer` -> `AnalysisResult.dependencies` -> `serialize_dependencies()` -> JSON-safe dict -> `DependencyResponse` validation -> `AnalysisResponse`.
- **`DependencyResponse`**: Typed API model with `type` (string value, e.g. `"CALL"`), `target` (preserved exactly as extracted), and `source_location` (`PositionResponse | None`).
- **`PositionResponse`**: Typed API model preserving every field emitted by the serializer: `type`, `line`, `column`, `offset`, `filename`.
- **Serialization Reuse**: `serialize_dependencies()` remains the source of dependency serialization; the API schema only validates the produced dicts.
- **Empty Behavior**: `dependencies` remains present and `[]` when no dependencies are extracted.
- **Deduplication**: Task-051 deduplication remains unchanged; no deduplication logic added in the API layer.

## Validation
- `pytest tests/analysis/dependencies -q` — dependency unit tests pass.
- `pytest tests/analysis -q` — analysis API suite passes.
- `pytest tests/integration -q` — integration suite passes.
- `pytest -q` — full suite passes (only pre-existing parser/IR baseline failures remain, unrelated to this task).
- `ruff check .` — no violations introduced by this task.
- `black --check .` — formatting clean for changed files.
- `python -m mypy app` — type checks pass.
- `git diff --check` — no whitespace errors.
