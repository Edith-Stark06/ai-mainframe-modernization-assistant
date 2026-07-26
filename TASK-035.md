# TASK-035 — Java Arithmetic Generation

## Objective

Extend the Java backend to translate arithmetic IR instructions into executable Java statements. This milestone introduces support for generating Java code for basic arithmetic operations while maintaining deterministic output and backend diagnostics.

---

## Background

Task-032 established Java class generation.

Task-033 added Java field generation.

Task-034 introduced executable Java statement generation for MOVE and DISPLAY instructions.

The backend can now generate Java assignments and output statements. This task expands executable code generation to support COBOL arithmetic operations.

---

## Scope

Implement Java statement generation for the following IR instructions:

- ADD
- SUBTRACT
- MULTIPLY
- DIVIDE

Generated statements should appear inside the generated `main()` method alongside existing MOVE and DISPLAY translations.

This milestone does **not** include:

- IF statements
- PERFORM loops
- EVALUATE
- CALL
- File I/O
- Exception handling

---

# Functional Requirements

## 1. Translate ADD

Support translation of IR ADD instructions.

Example:

IR

```
ADD 5 TO WS-COUNT
```

Generated Java

```java
wsCount += 5;
```

Example

```
ADD WS-VALUE TO WS-TOTAL
```

Generated Java

```java
wsTotal += wsValue;
```

---

## 2. Translate SUBTRACT

Support translation of IR SUBTRACT instructions.

Example

```
SUBTRACT 2 FROM WS-COUNT
```

Generated Java

```java
wsCount -= 2;
```

Example

```
SUBTRACT WS-LOSS FROM WS-TOTAL
```

Generated Java

```java
wsTotal -= wsLoss;
```

---

## 3. Translate MULTIPLY

Support translation of IR MULTIPLY instructions.

Example

```
MULTIPLY 2 BY WS-COUNT
```

Generated Java

```java
wsCount *= 2;
```

---

## 4. Translate DIVIDE

Support translation of IR DIVIDE instructions.

Example

```
DIVIDE 2 INTO WS-TOTAL
```

Generated Java

```java
wsTotal /= 2;
```

Division should preserve the semantics already represented in the IR. Any semantic validation (such as divide-by-zero detection, if applicable) remains the responsibility of earlier compiler phases unless explicitly represented in the IR.

---

## 5. Operand Translation

Arithmetic instructions must support:

- integer literals
- decimal literals
- variable operands
- combinations of literals and variables

Variable names must use the existing Java naming conversion.

Example

```
WS-COUNT
```

↓

```java
wsCount
```

---

## 6. Preserve Statement Order

Generated arithmetic statements must preserve the order of instructions in the IR.

Example

```
MOVE
ADD
DISPLAY
SUBTRACT
DISPLAY
```

must generate Java in the same order.

---

## 7. Backend Diagnostics

Generate backend diagnostics for:

- unsupported arithmetic instruction formats
- unsupported operand types
- malformed arithmetic instructions

Generation should continue whenever possible.

---

## 8. Deterministic Output

Generating Java from identical IR must always produce identical output.

The generated source must never contain:

- timestamps
- UUIDs
- random values
- machine-specific information

---

# Testing

Create or extend:

```
tests/backend/test_java_statements.py
```

Cover at least:

- ADD literal
- ADD variable
- SUBTRACT literal
- SUBTRACT variable
- MULTIPLY literal
- MULTIPLY variable
- DIVIDE literal
- DIVIDE variable
- Mixed arithmetic sequence
- Statement ordering
- Unsupported arithmetic diagnostics
- Deterministic output

---

# Documentation

Update:

```
docs/architecture/backend.md
```

Document:

- Arithmetic statement generation
- Operand translation
- Java arithmetic emission strategy
- Supported arithmetic instructions

---

# Acceptance Criteria

- ADD translated correctly
- SUBTRACT translated correctly
- MULTIPLY translated correctly
- DIVIDE translated correctly
- Operand translation verified
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

- IF translation
- PERFORM translation
- EVALUATE translation
- CALL translation
- File operations
- Java project generation
- Runtime optimizations

---

# Branch

```
feat/task-035
```

---

# Files to Modify

```
app/backend/java/statement_emitter.py
app/backend/java/generator.py
tests/backend/test_java_statements.py
docs/architecture/backend.md
```

Additional helper modules may be added if they improve maintainability.

---

# Deliverables

- Java ADD translation
- Java SUBTRACT translation
- Java MULTIPLY translation
- Java DIVIDE translation
- Backend diagnostics for arithmetic
- Comprehensive unit tests
- Updated backend architecture documentation