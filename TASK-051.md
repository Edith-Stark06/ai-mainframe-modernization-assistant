# TASK-051: Dependency Analyzer Foundation

## Objective
Implement a deterministic Dependency Analyzer foundation that extracts COBOL dependencies from the existing parsed representation (AST).

## Scope
- Define typed representations for dependencies.
- Traverse the existing AST and extract dependencies using the visitor pattern.
- Implement tests to verify deterministic dependency extraction, deduplication, and source location preservation.

## Non-goals
- Modifying the parser or lexer to support syntax that is not currently represented in the AST (e.g., `COPY` statements).
- Resolving external dependencies to the filesystem.
- Building the REST API endpoint (this will be a future task).
- Semantic validation of dependencies (e.g., checking if a `CALL` target actually exists).

## Dependency Types

### Domain Model Support
The analyzer's domain model defines the following dependency types:
- `COPY`
- `CALL`
- `PERFORM`

### Supported by Current AST
The analyzer successfully extracts the following dependency types from the current AST representation:
- `CALL`
- `PERFORM`

### Current Limitation
- `COPY` cannot be extracted because the current parser does not represent `COPY` statements in the AST. The lexer typically processes `COPY` directives before the AST is built. The Dependency Analyzer intentionally does not fabricate `COPY` dependencies from unsupported AST inputs.

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
- [x] Test supported `CALL` and `PERFORM` dependencies, and explicitly verify the `COPY` extraction limitation.
- [x] Test duplicate dependency handling.
- [x] Run validation commands.

## Testing Requirements
- Unit tests are located in `tests/analysis/dependencies/test_analyzer.py` covering:
  - `CALL` dependency.
  - `PERFORM` dependency.
  - Nested supported statements inside `IF` and `PERFORM UNTIL`.
  - Multiple dependencies in one program.
  - Duplicate dependency handling.
  - Program with no dependencies.
  - Source-location preservation.
  - Explicit testing of the `COPY` parser limitation without fake extractions.
