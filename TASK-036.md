# TASK-036 — Java Control Flow Generation

## Objective

Extend the Java backend to translate IR control flow instructions into executable Java control structures. This milestone introduces support for conditional branching while maintaining deterministic output and backend diagnostics.

---

## Background

Task-032 established Java class generation.

Task-033 added Java field generation.

Task-034 introduced executable Java statement generation for MOVE and DISPLAY.

Task-035 added arithmetic statement generation for ADD, SUBTRACT, MULTIPLY, and DIVIDE.

The backend can now generate sequential executable Java code. This task expands code generation to support control flow.

---

## Scope

Implement Java code generation for the following IR control-flow instructions:

- IF
- ELSE
- END-IF

The generated Java should emit equivalent conditional blocks using standard Java syntax.

This milestone does **not** include:

- PERFORM
- EVALUATE
- CALL
- GO TO
- Exception handling
- File I/O

---

# Functional Requirements

## 1. Translate IF Statements

Support translation of IR IF instructions.

Example

IR

```
IF WS-COUNT > 0
    DISPLAY "POSITIVE"
END-IF
```

Generated Java

```java
if (wsCount > 0) {
    System.out.println("POSITIVE");
}
```

Support comparison operators:

- ==
- !=
- >
- >=
- <
- <=

---

## 2. Translate IF-ELSE

Example

IR

```
IF WS-COUNT > 0
    DISPLAY "POSITIVE"
ELSE
    DISPLAY "ZERO OR NEGATIVE"
END-IF
```

Generated Java

```java
if (wsCount > 0) {
    System.out.println("POSITIVE");
} else {
    System.out.println("ZERO OR NEGATIVE");
}
```

---

## 3. Translate Nested IF Statements

Support nested conditional blocks.

Example

```
IF A
    IF B
        DISPLAY "YES"
    END-IF
END-IF
```

Generate properly nested Java blocks.

---

## 4. Condition Translation

Support operands including:

- integer literals
- decimal literals
- string literals (when represented in the IR)
- variables

Reuse the existing Java identifier conversion.

Example

```
WS-COUNT
```

↓

```java
wsCount
```

---

## 5. Block Management

The backend should correctly manage:

- opening braces `{`
- closing braces `}`
- indentation
- nested blocks

Generated Java should be consistently formatted.

---

## 6. Preserve Statement Order

Conditional statements and enclosed instructions must appear in the same order as represented in the IR.

---

## 7. Backend Diagnostics

Generate diagnostics for:

- unsupported comparison operators
- malformed conditions
- unmatched IF / END-IF
- unsupported control-flow instructions

Generation should continue whenever possible.

---

## 8. Deterministic Output

Generating Java from identical IR must always produce identical output.

Do not generate:

- timestamps
- UUIDs
- random values
- environment-specific information

---

# Testing

Create or extend:

```
tests/backend/test_java_statements.py
```

Cover at least:

- Simple IF
- IF with ELSE
- Nested IF
- Comparison operators
- Variable comparisons
- Literal comparisons
- Statement ordering
- Diagnostics
- Deterministic output

---

# Documentation

Update:

```
docs/architecture/backend.md
```

Document:

- Control-flow generation
- Condition translation
- Block generation
- Indentation strategy
- Supported control-flow instructions

---

# Acceptance Criteria

- IF translated correctly
- ELSE translated correctly
- Nested IF supported
- Comparison operators translated correctly
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

- PERFORM
- GO TO
- CALL
- EVALUATE
- File handling
- Java project generation
- Runtime optimization

---

# Branch

```
feat/task-036
```

---

# Files to Modify

```
app/backend/java/statement_emitter.py
app/backend/java/generator.py
tests/backend/test_java_statements.py
docs/architecture/backend.md
```

Additional helper modules may be introduced if they improve readability and maintainability.

---

# Deliverables

- Java IF generation
- Java ELSE generation
- Nested IF support
- Condition translation
- Backend diagnostics
- Comprehensive unit tests
- Updated backend architecture documentation