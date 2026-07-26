# TASK-037 — Java PERFORM Translation

## Objective

Extend the Java backend to translate structured PERFORM IR instructions into equivalent Java loop constructs while preserving execution order, nesting, and deterministic output.

---

## Background

Completed backend milestones:

- Task-032 — Java class generation
- Task-033 — Java field generation
- Task-034 — MOVE & DISPLAY translation
- Task-035 — Arithmetic translation
- Task-036 — IF / ELSE translation

The backend now supports sequential execution and conditional branching. This task introduces loop generation.

---

# Scope

Implement Java generation for:

- PERFORM UNTIL
- END-PERFORM

This milestone does **not** include:

- PERFORM VARYING
- GO TO
- CALL
- EVALUATE
- Exception handling
- File I/O

---

# Functional Requirements

## 1. Translate PERFORM UNTIL

Example IR

```
PERFORM UNTIL WS-COUNT >= 10
    ADD 1 TO WS-COUNT
END-PERFORM
```

Generated Java

```java
while (!(wsCount >= 10)) {
    wsCount += 1;
}
```

---

## 2. Nested PERFORM

Support nested loops.

Example

```
PERFORM UNTIL A
    PERFORM UNTIL B
        DISPLAY "X"
    END-PERFORM
END-PERFORM
```

Generate correctly nested Java blocks.

---

## 3. Condition Translation

Reuse the condition translation implemented in Task-036.

Supported operators:

- ==
- !=
- >
- >=
- <
- <=

Operands:

- variables
- integer literals
- decimal literals
- string literals (when represented in the IR)

---

## 4. Block Management

Generate:

- opening braces
- closing braces
- indentation
- nested loop depth

---

## 5. Preserve Statement Order

Loop bodies must preserve IR instruction order exactly.

---

## 6. Backend Diagnostics

Generate diagnostics for:

- malformed PERFORM conditions
- unsupported operators
- unmatched END-PERFORM
- unsupported PERFORM variants

Generation should continue whenever possible.

---

## 7. Deterministic Output

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

- Simple PERFORM UNTIL
- Nested PERFORM
- Mixed IF inside PERFORM
- Mixed PERFORM inside IF
- Diagnostics
- Statement ordering
- Deterministic output

---

# Documentation

Update:

```
docs/architecture/backend.md
```

Document:

- PERFORM translation strategy
- Loop generation
- Nesting management
- Supported PERFORM constructs

---

# Acceptance Criteria

- PERFORM UNTIL translated correctly
- Nested loops supported
- Conditions translated correctly
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

- PERFORM VARYING
- GO TO
- CALL
- EVALUATE
- File handling
- Java project generation

---

# Branch

```
feat/task-037
```

---

# Files to Modify

```
app/backend/java/generator.py
app/backend/java/control_flow_emitter.py
tests/backend/test_java_statements.py
docs/architecture/backend.md
```

Additional helper modules may be added if they improve maintainability.

---

# Deliverables

- Java PERFORM UNTIL translation
- Nested loop support
- Backend diagnostics
- Comprehensive unit tests
- Updated backend documentation