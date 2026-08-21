# TASK-051: Dependency Analyzer Foundation

## Objective
Implement a deterministic Dependency Analyzer foundation that extracts COBOL dependencies from the existing parsed representation (AST).

## Scope
- Define typed representations for dependencies (`COPY`, `CALL`, `PERFORM`).
- Traverse the existing AST and extract dependencies using the visitor pattern.
- Implement tests to verify deterministic dependency extraction, deduplication, and source location preservation.

## Non-goals
- Modifying the parser or lexer to support syntax that is not currently represented in the AST (e.g. `COPY` statements).
- Resolving external dependencies to the filesystem.
- Building the REST API endpoint (this will be a future task).
- Semantic validation of dependencies (e.g., checking if a `CALL` target actually exists).

## Dependency Types
The analyzer targets the following dependency types:
- `COPY`
- `CALL`
- `PERFORM`

## Architecture
The dependency analysis package is located at `app/analysis/dependencies/`:
- `models.py`: Contains `DependencyType` (Enum) and `Dependency` (dataclass).
- `analyzer.py`: Contains `DependencyAnalyzer` which extends `ASTVisitor` to traverse the AST and extract dependencies deterministically.
- `__init__.py`: Exposes the public API for the package.

## Acceptance Criteria
- [x] Create an appropriate package structure `app/analysis/dependencies/`.
- [x] Distinguish at minimum: `COPY`, `CALL`, `PERFORM`.
- [x] Create a typed immutable `Dependency` model.
- [x] Implement a deterministic analyzer `DependencyAnalyzer`.
- [x] Preserve source location information where available.
- [x] Test `COPY` (documented limitation), `CALL`, and `PERFORM` dependencies.
- [x] Test duplicate dependency handling.
- [x] Run validation commands.

## Limitations
- **COPY Statement Parsing:** The current COBOL parser does not represent `COPY` statements as AST nodes. Consequently, the Dependency Analyzer cannot extract `COPY` dependencies from the AST. This is an explicit limitation in accordance with the task instructions ("If a syntax form is not represented by the current parser, DO NOT modify the parser").

## Testing Requirements
- Unit tests are located in `tests/analysis/dependencies/test_analyzer.py` covering:
  - `CALL` dependency.
  - `PERFORM` dependency.
  - `COPY` dependency (verified as unsupported).
  - Multiple dependencies in one program.
  - Duplicate dependency handling.
  - Program with no dependencies.
  - Source-location preservation.