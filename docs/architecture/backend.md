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
        ├── generator.py            ← Java class generation (TASK-032/033/034)
        ├── naming.py               ← COBOL → lowerCamelCase (TASK-033)
        ├── statement_emitter.py    ← MOVE/DISPLAY/Arithmetic → Java statements (TASK-034/035)
        └── type_mapper.py          ← CobolType → Java type (TASK-033)
```

Future backend tasks will add:

```
app/
└── backend/
    └── java/
        └── project_generator.py   (future)
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

        wsGreeting = "WELCOME";
        System.out.println(wsGreeting);
        wsCount += 5;

    }

}
```

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
| `IRInstruction` | Java statement |
| `IRDisplay` | `System.out.println(...)` |
| `IRMove` / `IRAssignment` | Variable assignment (`=`) |
| `IRAdd` | Compound assignment (`+=`) |
| `IRSubtract` | Compound assignment (`-=`) |
| `IRMultiply` | Compound assignment (`*=`) |
| `IRDivide` | Compound assignment (`/=`) |
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
| TASK-034 | ✅ MOVE/DISPLAY → Java statements |
| TASK-035 | ✅ ADD/SUBTRACT/MULTIPLY/DIVIDE → Java arithmetic statements |
| TASK-036 | Control-flow (IF, PERFORM, EVALUATE) translation |
| TASK-037 | CALL translation |
| TASK-038 | Java compilation validation |

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
| `BE004` | WARNING | IRMove/IRDisplay has empty operand or target. |
| `BE005` | WARNING | Unsupported IR instruction type in statement emitter. |
| `BE006` | WARNING | Arithmetic instruction has empty result, empty operand, or unsupported multi-operand form. |

---

## Statement Generation (TASK-034)

### Overview

Executable IR instructions are translated into Java statements inside the `main()` method.

```
IRInstruction (in entry basic block)
    ↓
emit_statement()    app.backend.java.statement_emitter
    ↓
_collect_statements()   app.backend.java.generator
    ↓
_render_class()         app.backend.java.generator
    ↓
        <statement>;  (inside main method body)
```

### Supported Instructions (TASK-034)

| IR Instruction | Java Output | Notes |
|----------------|-------------|-------|
| `IRMove(result, source)` | `<target> = <source>;` | Operands translated via `_translate_operand()` |
| `IRDisplay(operand)` | `System.out.println(<operand>);` | Quoted strings passed as-is |
| All others | `// TODO: translate <type>` | `BE005` WARNING emitted |

### Operand Translation

Defined in `app/backend/java/statement_emitter._translate_operand()`:

| IR Operand | Java Expression |
|------------|-----------------|
| `"HELLO"` (quoted) | `"HELLO"` (unchanged) |
| `42` (numeric integer) | `42` (unchanged) |
| `3.14` (numeric decimal) | `3.14` (unchanged) |
| `-5` (negative integer) | `-5` (unchanged) |
| `WS-GREETING` (identifier) | `wsGreeting` (lowerCamelCase) |

The translation rules are applied in order:

1. **Quoted string literal** — operand starts and ends with `"`: returned unchanged.
2. **Numeric literal** — matches `[-+]?\d+(\.\d+)?`: returned unchanged.
3. **COBOL identifier** — everything else: converted to lowerCamelCase via `to_java_field_name()`.

### Generated Example

IR instructions:

```
MOVE "WELCOME" -> WS-GREETING
DISPLAY WS-GREETING
MOVE 1 -> WS-COUNT
DISPLAY WS-COUNT
```

Generated Java:

```java
        wsGreeting = "WELCOME";
        System.out.println(wsGreeting);
        wsCount = 1;
        System.out.println(wsCount);
```

### Statement Ordering

Statements are emitted in the **same order** as they appear in the IR basic block.
No reordering, hoisting, or optimisation is applied at this stage.

---

## Arithmetic Statement Generation (TASK-035)

### Overview

TASK-035 extends `statement_emitter.py` to translate COBOL arithmetic IR instructions
into Java compound-assignment statements.  The same `_translate_operand()` helper and
`to_java_field_name()` naming strategy used for MOVE and DISPLAY are reused unchanged.

### Arithmetic Emission Strategy

All four arithmetic operations follow the same **compound-assignment** pattern:

```
<java_result> <operator> <java_left>;
```

Where:

- `<java_result>` — the accumulator variable, derived from `instruction.result` via
  `to_java_field_name()`.
- `<operator>` — the Java compound-assignment operator for the operation.
- `<java_left>` — the applied operand, derived from `instruction.left` via
  `_translate_operand()`.

The `instruction.right` field is reserved for future multi-operand support.  If it is
non-empty and differs from `instruction.result`, a `BE006` WARNING is emitted and the
field is ignored (graceful degradation).

### Supported Arithmetic Instructions

| IR Instruction | Operator | Generated Java | COBOL Equivalent |
|----------------|----------|----------------|------------------|
| `IRAdd(result, left)` | `+=` | `<result> += <left>;` | `ADD <left> TO <result>` |
| `IRSubtract(result, left)` | `-=` | `<result> -= <left>;` | `SUBTRACT <left> FROM <result>` |
| `IRMultiply(result, left)` | `*=` | `<result> *= <left>;` | `MULTIPLY <left> BY <result>` |
| `IRDivide(result, left)` | `/=` | `<result> /= <left>;` | `DIVIDE <left> INTO <result>` |

### Operand Support

All operand types supported by MOVE and DISPLAY are equally supported for arithmetic:

| Operand Type | IR Example | Generated Java |
|--------------|------------|----------------|
| Integer literal | `5` | `5` |
| Decimal literal | `1.5` | `1.5` |
| Negative literal | `-3` | `-3` |
| Variable | `WS-VALUE` | `wsValue` |
| Multi-segment variable | `WS-LINE-ITEM` | `wsLineItem` |

### Generated Example

IR instructions:

```
MOVE 0 -> WS-COUNT
ADD 5 TO WS-COUNT
DISPLAY WS-COUNT
SUBTRACT 2 FROM WS-COUNT
MULTIPLY 3 BY WS-COUNT
DIVIDE 6 INTO WS-COUNT
DISPLAY WS-COUNT
```

Generated Java:

```java
        wsCount = 0;
        wsCount += 5;
        System.out.println(wsCount);
        wsCount -= 2;
        wsCount *= 3;
        wsCount /= 6;
        System.out.println(wsCount);
```

### Statement Ordering

Arithmetic statements, like all other statements, are emitted in **exactly the same
order** as they appear in the IR basic block.  No reordering is performed.

### Arithmetic Diagnostics

| Code | Severity | Trigger |
|------|----------|---------| 
| `BE006` | WARNING | `instruction.result` is empty (no accumulator target). |
| `BE006` | WARNING | `instruction.left` is empty (no operand to apply). |
| `BE006` | WARNING | `instruction.right` is non-empty and differs from `result` (multi-operand form not yet supported; `right` is ignored). |

Generation **continues** when a `BE006` is emitted.  A malformed arithmetic instruction
is skipped (produces no Java statement), but subsequent instructions are unaffected.

### Divide-By-Zero

The backend emitter does not detect divide-by-zero.  This is the responsibility of
earlier compiler phases (semantic analysis or IR validation).  The emitter faithfully
translates whatever operand appears in `instruction.left`, including the literal `0`.

---

## Non-Goals

The backend does **not**:

- Parse COBOL source.
- Run semantic analysis.
- Build the IR (that is the IR builder's responsibility).
- Write files to disk (the compiler driver or API layer does that).
- Invoke `javac` or any external toolchain.
- Generate IF, PERFORM, EVALUATE, or CALL statements (deferred to future tasks).
- Generate Java project scaffolding or `pom.xml` (deferred to future tasks).
