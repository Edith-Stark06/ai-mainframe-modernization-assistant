# TASK-038 — Java CALL Translation

## Objective

Extend the Java backend to translate CALL IR instructions into Java method invocations. This milestone enables the backend to generate executable Java for procedure calls while maintaining deterministic output and backend diagnostics.

---

## Background

Completed backend milestones:

- Task-032 — Java class generation
- Task-033 — Java field generation
- Task-034 — MOVE & DISPLAY translation
- Task-035 — Arithmetic translation
- Task-036 — IF / ELSE translation
- Task-037 — PERFORM UNTIL translation

The backend now supports sequential execution, arithmetic, conditionals, and loops. This task introduces procedure invocation.

---

# Scope

Implement Java generation for:

- CALL

This milestone does **not** include:

- Dynamic program loading
- Reflection
- External process execution
- File I/O
- Runtime dependency injection

---

# Functional Requirements

## 1. Translate CALL

Example IR

```
CALL "CALCULATE-TOTAL"
```

Generated Java

```java
calculateTotal();
```

The Java method name should follow the existing identifier conversion strategy.

---

## 2. CALL With Arguments

Example

```
CALL "UPDATE-ACCOUNT"
USING WS-ID WS-BALANCE
```

Generated Java

```java
updateAccount(wsId, wsBalance);
```

Support:

- variables
- integer literals
- decimal literals
- string literals

Reuse the existing operand translation.

---

## 3. Preserve Statement Order

Generated CALL statements must appear exactly where represented in the IR.

---

## 4. Backend Diagnostics

Generate diagnostics for:

- unsupported CALL forms
- malformed argument lists
- invalid procedure names

Generation should continue whenever possible.

---

## 5. Deterministic Output

Generated Java must never contain:

- timestamps
- UUIDs
- random values
- machine-specific information

---

# Testing

Extend:

```
tests/backend/test_java_statements.py
```

Cover:

- CALL without arguments
- CALL with arguments
- Mixed CALL and arithmetic
- CALL inside IF
- CALL inside PERFORM
- Diagnostics
- Deterministic output

---

# Documentation

Update:

```
docs/architecture/backend.md
```

Document:

- CALL translation strategy
- Argument translation
- Method name conversion
- Supported CALL forms

---

# Acceptance Criteria

- CALL translated correctly
- Arguments translated correctly
- Statement ordering preserved
- Backend diagnostics implemented
- Deterministic output maintained
- Ruff passes
- Black passes
- MyPy passes
- Full Pytest suite passes

---

# Non-goals

Do **not** implement:

- Reflection
- Dynamic class loading
- RPC
- File handling
- Spring Boot project generation

---

# Branch

```
feat/task-038
```

---

# Files to Modify

```
app/backend/java/statement_emitter.py
app/backend/java/generator.py
tests/backend/test_java_statements.py
docs/architecture/backend.md
```

Additional helper modules may be introduced if they improve maintainability.

---

# Deliverables

- Java CALL translation
- Argument translation
- Backend diagnostics
- Comprehensive unit tests
- Updated backend documentation