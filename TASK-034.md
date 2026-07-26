# TASK-034 — Java Statement Generation

## Objective

Extend the Java backend to translate executable IR instructions into Java statements. This milestone introduces backend support for generating executable Java code from the IR while maintaining deterministic output and backend diagnostics.

---

## Background

Task-032 established Java class generation.

Task-033 added Java field generation from IR data declarations.

The backend can now generate a complete Java class with fields, but the generated `main()` method remains empty.

Example output:

```java
public class Hello {

    private String wsGreeting = "WELCOME";
    private int wsCount = 1;

    public static void main(String[] args) {

    }

}
```

This task begins translating executable IR instructions into Java statements.

---

## Scope

Implement Java statement generation for the following IR instructions:

- MOVE
- DISPLAY

Generated statements should appear inside the generated `main()` method.

This milestone does **not** include arithmetic, control flow, procedure calls, or Java project generation.

---

# Functional Requirements

## 1. Generate Java Statements

Extend:

```
app/backend/java/generator.py
```

to emit executable Java statements.

Example output:

```java
public class Hello {

    private String wsGreeting = "WELCOME";
    private int wsCount = 1;

    public static void main(String[] args) {

        wsGreeting = "HELLO";
        System.out.println(wsGreeting);

    }

}
```

---

## 2. Translate MOVE Instructions

Support translation of IR MOVE instructions.

Examples:

IR:

```
MOVE "HELLO" -> WS-GREETING
```

Generated Java:

```java
wsGreeting = "HELLO";
```

IR:

```
MOVE 1 -> WS-COUNT
```

Generated Java:

```java
wsCount = 1;
```

Support:

- string literals
- numeric literals
- variable-to-variable assignments

---

## 3. Translate DISPLAY Instructions

Support translation of IR DISPLAY instructions.

Examples:

IR:

```
DISPLAY "HELLO"
```

Generated Java:

```java
System.out.println("HELLO");
```

IR:

```
DISPLAY WS-GREETING
```

Generated Java:

```java
System.out.println(wsGreeting);
```

---

## 4. Preserve Statement Order

Statements must be emitted in the same order as they appear in the IR.

Example:

```
MOVE ...
DISPLAY ...
MOVE ...
DISPLAY ...
```

must generate:

```java
assignment
println
assignment
println
```

without reordering.

---

## 5. Backend Diagnostics

Generate backend diagnostics for:

- unsupported instruction types
- unsupported operands
- invalid assignments

The backend should continue generating Java whenever possible.

---

## 6. Deterministic Output

Generating Java multiple times from identical IR must always produce identical output.

The generated source must not contain:

- timestamps
- UUIDs
- random values
- environment-specific information

---

# Testing

Create or extend:

```
tests/backend/test_java_generator.py
```

or

```
tests/backend/test_java_statements.py
```

Cover at least:

- MOVE string literal
- MOVE numeric literal
- MOVE variable-to-variable
- DISPLAY string literal
- DISPLAY variable
- Multiple statements
- Statement ordering
- Unsupported instruction diagnostics
- Deterministic output

---

# Documentation

Update:

```
docs/architecture/backend.md
```

Document:

- Statement generation pipeline
- MOVE translation
- DISPLAY translation
- Backend emission strategy

---

# Acceptance Criteria

- Java assignments generated for MOVE
- Java println statements generated for DISPLAY
- Statement ordering preserved
- Backend diagnostics implemented
- Deterministic output
- Ruff passes
- Black passes
- MyPy passes
- Full Pytest suite passes

---

# Non-goals

Do **not** implement:

- Arithmetic translation
- IF statement translation
- PERFORM translation
- CALL translation
- Java compilation
- Spring Boot project generation
- File writing

---

# Branch

```
feat/task-034
```

---

# Files to Modify

```
app/backend/java/generator.py
tests/backend/test_java_generator.py
docs/architecture/backend.md
```

Additional helper modules may be introduced if they improve maintainability.

---

# Deliverables

- Java MOVE translation
- Java DISPLAY translation
- Statement ordering
- Backend diagnostics
- Comprehensive unit tests
- Updated backend architecture documentation