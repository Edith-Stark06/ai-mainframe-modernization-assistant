# TASK-040 — Regression Test Suite

## Objective

Establish a comprehensive regression test suite to ensure that existing compiler functionality continues to work correctly as new features are added. The regression suite should protect every compiler stage from unintended behavioral changes.

---

## Background

The compiler now has:

- Unit tests for individual components
- End-to-end integration tests
- Java backend translation support

This task introduces a centralized regression suite containing representative COBOL programs that will be executed automatically during continuous integration.

---

# Scope

Create a dedicated regression testing framework built around real COBOL programs.

The regression suite should verify:

```
COBOL Source
      ↓
Compiler Pipeline
      ↓
Generated Java
      ↓
Regression Assertions
```

These tests should serve as the primary safety net for future compiler development.

---

# Functional Requirements

## 1. Create Regression Test Structure

Create:

```
tests/regression/
```

---

## 2. Regression Fixture Library

Organize representative COBOL programs into categories.

Example:

```
tests/regression/fixtures/

basic/
    hello_world.cbl
    move_display.cbl

arithmetic/
    add.cbl
    subtract.cbl
    multiply.cbl
    divide.cbl

control_flow/
    if_else.cbl
    nested_if.cbl

loops/
    perform_until.cbl

procedures/
    call.cbl

combined/
    inventory_program.cbl
    payroll_program.cbl

invalid/
    invalid_syntax.cbl
    undefined_variable.cbl
```

Fixtures should be easy to extend as the compiler grows.

---

## 3. Regression Runner

Implement reusable helpers that:

- discover fixture programs automatically
- execute the compiler pipeline
- collect diagnostics
- validate output
- report failures clearly

Avoid manually registering every fixture.

---

## 4. Expected Assertions

Regression tests should verify:

- translation succeeds
- diagnostics match expectations
- generated Java contains expected constructs
- no compiler crashes occur
- deterministic output

Do not compare complete Java source yet.

---

## 5. Failure Reporting

Regression failures should clearly identify:

- fixture name
- compiler stage
- assertion failure
- diagnostics (if any)

Failure output should make debugging straightforward.

---

## 6. Deterministic Execution

Running the regression suite multiple times should always produce identical results.

---

## 7. Extensibility

Adding a new regression test should require only:

1. adding a fixture
2. defining expected assertions (if necessary)

The framework should automatically include it.

---

# Testing

Run:

```bash
black --check .
ruff check .
mypy app
pytest
pytest tests/regression -v
```

All tests must pass.

---

# Documentation

Update:

```
docs/testing.md
```

Document:

- regression testing philosophy
- fixture organization
- adding new regression tests
- expected workflow for future contributors

---

# Acceptance Criteria

- `tests/regression/` created
- fixture discovery implemented
- reusable regression runner created
- categorized fixture library added
- deterministic execution verified
- clear failure reporting implemented
- documentation updated
- Black passes
- Ruff passes
- MyPy passes
- Full Pytest suite passes

---

# Non-goals

Do **not** implement:

- Golden file comparisons
- Java compilation tests
- Performance benchmarks
- Project generation

These belong to later milestones.

---

# Branch

```
feat/task-040
```

---

# Files to Add

```
tests/regression/
tests/regression/fixtures/
docs/testing.md
```

Additional helper modules may be added to improve maintainability.

---

# Deliverables

- Regression testing framework
- Categorized COBOL fixture library
- Automatic fixture discovery
- Reusable regression runner
- Updated testing documentation