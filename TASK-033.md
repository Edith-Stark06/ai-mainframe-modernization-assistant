# TASK-033 — Java Variable & Data Division Generation

## Objective

Extend the Java backend to translate IR data declarations into Java class fields. This milestone introduces backend support for COBOL Working-Storage variables while keeping executable statement generation out of scope.

---

## Background

Task-032 established the Java backend foundation and generated a deterministic Java class skeleton from the IR.

Example output:

```java
public class Hello {

    public static void main(String[] args) {

    }

}
```

The backend can now generate a valid Java class but does not yet represent COBOL data items.

This task adds support for generating Java fields corresponding to IR variable declarations.

---

## Scope

Implement Java field generation for IR data declarations.

Supported functionality:

- Java field declarations
- Java type mapping
- Field naming
- Optional initial values
- Backend diagnostics
- Deterministic output

This task does **not** generate executable Java statements.

---

# Functional Requirements

## 1. Generate Java Fields

Extend:

```
app/backend/java/generator.py
```

to emit Java instance fields before the `main()` method.

Example:

```java
public class Hello {

    private String wsGreeting = "WELCOME";
    private int wsCount = 1;

    public static void main(String[] args) {

    }

}
```

---

## 2. Java Type Mapping

Implement initial type mapping.

| IR Type | Java Type |
|----------|-----------|
| Alphanumeric | String |
| Integer | int |
| Decimal | double |
| Boolean | boolean |

Unsupported IR types should produce backend diagnostics instead of crashing.

---

## 3. Java Field Naming

Convert COBOL identifiers into lowerCamelCase Java field names.

Examples:

| COBOL | Java |
|--------|------|
| WS-COUNT | wsCount |
| CUSTOMER-NAME | customerName |
| EMPLOYEE-ID | employeeId |

Rules:

- lowerCamelCase
- remove hyphens
- preserve readability
- valid Java identifier

---

## 4. Initial Values

Generate field initializers whenever the IR provides one.

Example:

COBOL:

```cobol
01 WS-GREETING PIC X(20) VALUE "WELCOME".
01 WS-COUNT PIC 9(3) VALUE 1.
```

Generated Java:

```java
private String wsGreeting = "WELCOME";
private int wsCount = 1;
```

If no initial value exists:

```java
private String customerName;
```

---

## 5. Deterministic Output

Field ordering must remain deterministic.

Generating Java twice from identical IR must produce identical output.

No timestamps, UUIDs, random values, or environment-specific content may appear.

---

## 6. Backend Diagnostics

Report diagnostics for unsupported backend situations including:

- unsupported IR types
- invalid field identifiers
- unsupported initial values

The backend should continue generation whenever possible.

---

# Testing

Create or extend:

```
tests/backend/test_java_generator.py
```

Cover at least:

- String field generation
- Integer field generation
- Decimal field generation
- Boolean field generation
- Field naming conversion
- Field initialization
- Fields without initial values
- Multiple field ordering
- Deterministic output
- Backend diagnostics for unsupported types

---

# Documentation

Update:

```
docs/architecture/backend.md
```

Document:

- IR data translation
- Java type mapping
- Field naming strategy
- Backend generation pipeline

---

# Acceptance Criteria

- Java fields generated from IR
- Correct Java type mapping
- Correct field naming
- Initial values generated
- Deterministic output
- Backend diagnostics implemented
- Ruff passes
- Black passes
- MyPy passes
- All tests pass

---

# Non-goals

Do **not** implement:

- MOVE translation
- DISPLAY translation
- CALL translation
- Arithmetic generation
- Control-flow generation
- Java compilation
- Spring Boot project generation
- File writing

---

# Branch

```
feat/task-033
```

---

# Files to Modify

```
app/backend/java/generator.py
tests/backend/test_java_generator.py
docs/architecture/backend.md
```

Additional helper modules may be created if they improve maintainability.

---

# Deliverables

- Java field generation
- Java type mapping
- Field naming conversion
- Backend diagnostics
- Comprehensive unit tests
- Updated backend architecture documentation