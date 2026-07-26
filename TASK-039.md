# TASK-039 — End-to-End Translation Tests

## Objective

Implement end-to-end integration tests that validate the complete COBOL-to-Java translation pipeline. Each test should begin with COBOL source code, execute every compiler phase, and verify that the generated Java contains the expected constructs.

---

## Background

The compiler currently supports:

- Lexer
- Parser
- AST Construction
- Semantic Analysis
- Intermediate Representation (IR)
- Java Backend
  - Class Generation
  - Data Declaration Generation
  - MOVE
  - DISPLAY
  - Arithmetic Operations
  - IF / ELSE
  - PERFORM UNTIL
  - CALL

Each compiler stage already has dedicated unit tests. This task introduces **integration testing** to verify that all compiler phases work correctly together.

---

# Scope

Create an integration test suite that exercises the complete compiler pipeline.

```
COBOL Source
      ↓
Lexer
      ↓
Parser
      ↓
AST
      ↓
Semantic Analysis
      ↓
IR Generation
      ↓
Java Backend
      ↓
Generated Java
```

These tests should execute the real compiler pipeline without bypassing intermediate stages.

---

# Functional Requirements

## 1. Integration Test Structure

Create:

```
tests/integration/
```

This directory will contain all end-to-end compiler tests.

---

## 2. COBOL Fixture Programs

Create:

```
tests/fixtures/
```

Include representative COBOL programs such as:

```
hello_world.cbl
move_display.cbl
arithmetic.cbl
if_else.cbl
perform_until.cbl
call.cbl
combined_program.cbl
invalid_syntax.cbl
undefined_variable.cbl
```

Each valid fixture should be a complete standalone COBOL program.

---

## 3. Full Pipeline Execution

Each integration test must:

1. Read a COBOL fixture.
2. Execute the complete compiler pipeline.
3. Generate Java source code.
4. Verify successful completion.

No compiler stage should be skipped or mocked.

---

## 4. Generated Java Validation

Rather than comparing entire Java source files, verify that generated Java contains the expected constructs.

Examples:

### move_display.cbl

Expected Java contains:

```java
wsCount = 5;
System.out.println(wsCount);
```

---

### arithmetic.cbl

Expected Java contains:

```java
+=
-=
*=
/=
```

---

### if_else.cbl

Expected Java contains:

```java
if (
else {
```

---

### perform_until.cbl

Expected Java contains:

```java
while (
```

---

### call.cbl

Expected Java contains:

```java
calculateTotal(
```

---

### combined_program.cbl

Verify presence of:

- field declarations
- assignments
- arithmetic
- IF statements
- PERFORM loops
- CALL statements
- DISPLAY statements

---

## 5. Diagnostics Validation

Include invalid fixtures such as:

```
invalid_syntax.cbl
undefined_variable.cbl
```

Verify that:

- diagnostics are produced
- compiler fails gracefully when appropriate
- no unhandled exceptions occur

---

## 6. Deterministic Output

Running the compiler multiple times on the same COBOL fixture should always generate identical Java output.

No generated output may contain:

- timestamps
- UUIDs
- random identifiers
- machine-specific information

---

## 7. Reusable Test Helpers

Create helper utilities for:

- loading fixture files
- executing the compiler pipeline
- collecting diagnostics
- comparing generated output

Avoid duplicating pipeline setup across tests.

---

# Testing

Run:

```bash
black --check .
ruff check .
mypy app
pytest
pytest tests/integration -v
```

All quality checks must pass.

---

# Documentation

Create or update:

```
docs/testing.md
```

Document:

- integration testing philosophy
- fixture organization
- how to add new fixture programs
- how to execute integration tests
- deterministic output expectations

---

# Acceptance Criteria

- `tests/integration/` created
- `tests/fixtures/` created
- Complete compiler pipeline exercised
- Generated Java validated
- Invalid COBOL programs tested
- Diagnostics verified
- Deterministic output verified
- Reusable testing helpers added
- Documentation updated
- Black passes
- Ruff passes
- MyPy passes
- Full Pytest suite passes

---

# Non-goals

Do **not** implement:

- Golden file comparisons
- Java compilation tests
- Performance benchmarking
- Maven/Gradle project generation

Those belong to later milestones.

---

# Branch

```
feat/task-039
```

---

# Files to Add

```
tests/integration/
tests/fixtures/
docs/testing.md
```

Additional helper modules may be added if they improve maintainability and reduce duplication.

---

# Deliverables

- End-to-end integration test suite
- COBOL fixture programs
- Invalid input fixtures
- Reusable pipeline testing helpers
- Testing documentation