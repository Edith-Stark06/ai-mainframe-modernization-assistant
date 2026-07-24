# Backend Architecture

## Overview

The backend layer consumes the **Intermediate Representation (IR)** produced by the compiler frontend and emits target-language source code.

The backend is deliberately separated from the frontend (lexer → parser → semantic → IR) so each layer evolves independently.

---

## Pipeline Position

```
COBOL Source
    ↓
Lexer           app.parser.lexer
    ↓
Parser          app.parser.syntax
    ↓
Semantic        app.parser.semantic
    ↓
IR Builder      app.ir.builder
    ↓
IR Program      app.ir.program
    ↓
Java Generator  app.backend.java.generator   ← This document
    ↓
Java Source (string)
```

No file I/O occurs inside the generator.  The caller is responsible for writing the returned string to disk.

---

## Module Structure

```
app/
└── backend/
    ├── __init__.py
    └── java/
        ├── __init__.py
        ├── field_model.py          ← JavaField value object (TASK-033)
        ├── generator.py            ← Java class generation (TASK-032/033)
        ├── naming.py               ← COBOL → lowerCamelCase (TASK-033)
        └── type_mapper.py          ← CobolType → Java type (TASK-033)
```

Future backend tasks will add:

```
app/
└── backend/
    └── java/
        ├── statement_emitter.py   (TASK-034+)
        └── project_generator.py   (TASK-035+)
```

---

## Java Class Generation (TASK-032)

### Entry Points

| Symbol | Description |
|--------|-------------|
| `generate(program)` | Returns a Java source `str`. Logs diagnostics internally. |
| `generate_with_diagnostics(program)` | Returns `GenerationResult` with both source and diagnostics. |

### Class Name Derivation

The Java class name is derived from the IR in this priority order:

1. **First module name** — `program.modules[0].name` if non-empty.
2. **Program name** — `program.name` if non-empty.
3. **Default** — `"GeneratedProgram"` (emits a `BE001` WARNING diagnostic).

The raw name is sanitised by `_to_java_class_name()`:

- Splits on `-` and `_` (COBOL naming conventions).
- Capitalises the first letter of each segment.
  - All-uppercase / all-lowercase segments: fully normalised (`"HELLO"` → `"Hello"`).
  - Mixed-case segments: first letter uppercased, rest preserved (`"GeneratedProgram"` → `"GeneratedProgram"`).
- Strips characters invalid in Java identifiers.
- Prepends `"P"` if the result starts with a digit.
- Defaults to `"GeneratedProgram"` if the result is empty.

### Generated Structure

```java
public class Hello {

    public static void main(String[] args) {

        // IR: DISPLAY "HELLO WORLD"
        // IR: MOVE "WELCOME" -> WS-GREETING

    }

}
```

IR instruction stubs are emitted as `// IR:` comments inside `main`.  Full statement lowering is deferred to later tasks.

### Diagnostics

| Code | Severity | Trigger |
|------|----------|---------|
| `BE001` | WARNING | No program name and no named module found. |

Diagnostics are non-fatal.  A valid Java class skeleton is always produced.

---

## Relationship Between IR and Java

| IR Concept | Java Concept |
|------------|-------------|
| `IRProgram` | Compilation unit (one `.java` file per program) |
| `IRModule` | Java class |
| `IRFunction` | Java method |
| `IRBasicBlock` | Logical block inside a method |
| `IRInstruction` | Java statement (future lowering) |
| `IRDisplay` | `System.out.println(...)` (future) |
| `IRMove` / `IRAssignment` | Variable assignment (future) |
| `IRCall` | Method call (future) |
| `IRConditionalBranch` | `if` / `else` (future) |
| `IRJump` | `goto`-equivalent / loop structure (future) |

---

## Determinism Guarantee

The generator is a pure function — it never:

- Reads the clock.
- Uses random identifiers.
- Depends on hash-map iteration order.

Given identical `IRProgram` input, `generate()` always returns byte-for-byte identical output.

---

## Future Backend Tasks

| Task | Scope |
|------|-------|
| TASK-033 | ✅ Java field declarations from COBOL data items |
| TASK-034 | Statement lowering (DISPLAY → `System.out.println`) |
| TASK-035 | Spring Boot project skeleton generation |
| TASK-036 | Maven `pom.xml` generation |
| TASK-037 | Java compilation validation |

---

## Data Division Translation (TASK-033)

### Overview

COBOL Working-Storage variables are translated into Java instance field declarations.

```
VariableSymbol (semantic layer)
    ↓
build_fields_from_symbols()   app.backend.java.generator
    ↓
JavaField []                  app.backend.java.field_model
    ↓
_render_class()               app.backend.java.generator
    ↓
private <type> <name> [= <value>];
```

### Java Type Mapping

Defined in `app/backend/java/type_mapper.py`:

| COBOL Type | Condition | Java Type |
|------------|-----------|-----------|
| `AlphanumericType` | any | `String` |
| `NumericType` | `decimal_places == 0` | `int` |
| `NumericType` | `decimal_places > 0` | `double` |
| `GroupType` | any | `String` |

Unsupported types produce a `BE002` WARNING diagnostic.  Fields with no resolved
COBOL type produce a `BE003` WARNING.  Generation continues in both cases.

### Field Naming Strategy

Defined in `app/backend/java/naming.py` via `to_java_field_name()`:

| COBOL Name | Java Name |
|------------|-----------|
| `WS-COUNT` | `wsCount` |
| `CUSTOMER-NAME` | `customerName` |
| `EMPLOYEE-ID` | `employeeId` |
| `TOTAL` | `total` |

Rules:
1. Split on `-` and `_`.
2. First segment → all-lowercase.
3. Subsequent segments → `capitalize()` (first letter upper, rest lower).
4. Strip invalid Java identifier characters.
5. Prepend `f` if the result starts with a digit.
6. Default to `"field"` if the result is empty.

### Generated Example

COBOL Working-Storage:

```cobol
01 WS-GREETING PIC X(20) VALUE "WELCOME".
01 WS-COUNT    PIC 9(3)  VALUE 0.
01 WS-RATE     PIC 9(5)V99.
```

Generated Java:

```java
public class Hello {

    private String wsGreeting;
    private int wsCount;
    private double wsRate;

    public static void main(String[] args) {

    }

}
```

### Diagnostics

| Code | Severity | Trigger |
|------|----------|---------|
| `BE001` | WARNING | No program name and no named module. |
| `BE002` | WARNING | Unsupported COBOL type; no Java mapping defined. |
| `BE003` | WARNING | Variable symbol has no resolved COBOL type. |

---

## Non-Goals

The backend does **not**:

- Parse COBOL source.
- Run semantic analysis.
- Build the IR (that is the IR builder's responsibility).
- Write files to disk (the compiler driver or API layer does that).
- Invoke `javac` or any external toolchain.
