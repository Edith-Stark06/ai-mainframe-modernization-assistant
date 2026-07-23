# TASK-031 — Compiler Driver & IR Pretty Printer

## Objective

Create a standalone compiler driver that executes the complete frontend pipeline on a COBOL source file and prints the resulting Intermediate Representation.

This task provides an end-to-end executable for validating the compiler frontend before backend code generation begins.

---

## Background

The compiler frontend now supports:

- Lexer
- Parser
- AST
- Semantic Analysis
- Intermediate Representation

However, there is currently no executable entry point that runs the complete pipeline outside the FastAPI application.

This task introduces a dedicated compiler CLI.

---

## Scope

Implement a command-line compiler driver independent of the REST API.

The driver shall:

- Load a COBOL source file
- Parse the source
- Perform semantic analysis
- Build the Intermediate Representation
- Pretty-print the generated IR
- Report diagnostics
- Exit with an appropriate status code

---

## Functional Requirements

### 1. Compiler Driver

Create:

```
app/compiler.py
```

The compiler shall support:

```
python -m app.compiler examples/hello.cbl
```

The FastAPI application must remain unchanged.

---

### 2. Pipeline Execution

Execute the following stages in order:

```
Source File
    ↓
Lexer
    ↓
Parser
    ↓
Semantic Analysis
    ↓
IR Builder
```

Abort on unrecoverable failures.

---

### 3. Pretty Printer

Implement an IR pretty printer.

The output should resemble:

```
Program HELLO

Function MAIN

entry:

DISPLAY "HELLO"

MOVE 5 -> TOTAL

ADD TOTAL 10

STOP
```

The formatting should be deterministic.

---

### 4. Diagnostics

Print parser and semantic diagnostics in a readable form.

Example:

```
Semantic Errors:

Line 12:
Undefined variable TOTAL-AMOUNT
```

Exit with a non-zero status code when compilation fails.

---

### 5. Example Programs

Create:

```
examples/
```

Include representative COBOL programs demonstrating:

- DISPLAY
- MOVE
- Arithmetic
- IF / ELSE
- CALL

---

### 6. Documentation

Update:

```
README.md
```

Document:

- Running the compiler
- Example commands
- Expected output
- Purpose of the compiler driver

---

## Testing

Add tests covering:

- Successful compilation
- Missing source file
- Invalid source
- Pretty-printer output
- Exit codes

---

## Acceptance Criteria

- `python -m app.compiler <file>` works
- IR prints correctly
- Diagnostics are readable
- Deterministic output
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Java generation
- Spring Boot generation
- Optimization
- Backend code generation