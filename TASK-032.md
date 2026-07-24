# TASK-032 — IR → Java Class Generation

## Objective

Implement the initial Java backend by translating the Intermediate Representation (IR) into a compilable Java class skeleton.

This task establishes the backend generation pipeline while keeping statement generation minimal. The focus is on producing valid Java source code from the compiler IR.

---

## Background

The compiler now supports:

- Lexer
- Parser
- AST
- Semantic Analysis
- Intermediate Representation
- Compiler Driver
- IR Pretty Printer

The frontend is complete.

Task-032 begins the backend by introducing Java source generation from the Intermediate Representation.

---

## Scope

Implement a Java backend that consumes an `IRProgram` and generates a deterministic Java class.

Initially generate:

- Java class declaration
- Main method
- Entry-point structure

Statement translation is intentionally deferred to later tasks.

---

## Functional Requirements

### 1. Java Generator

Create:

```
app/backend/java/generator.py
```

Implement:

```python
generate(program: IRProgram) -> str
```

The generator shall return the complete Java source as a string.

Do not write files to disk.

---

### 2. Java Class Generation

Generate a valid Java class from the IR.

Example:

```java
public class Hello {

    public static void main(String[] args) {

    }

}
```

The class name shall be derived from the IR program or module name.

---

### 3. Backend Architecture

Keep the implementation modular.

Separate:

- Java generation
- Future statement lowering
- Future project generation

This task should establish the backend foundation without introducing Spring Boot generation.

---

### 4. Diagnostics

Produce backend diagnostics for:

- Missing program name
- Invalid module structure
- Unsupported IR layout

Fail gracefully without uncaught exceptions.

---

### 5. Deterministic Output

Generated Java source must be deterministic.

Avoid:

- timestamps
- random identifiers
- platform-specific formatting

---

## Testing

Add tests covering:

- Empty IR program
- Simple program
- Class generation
- Main method generation
- Deterministic output

---

## Documentation

Update:

```
docs/architecture/backend.md
```

Document:

- Backend pipeline
- Java class generation
- Relationship between IR and Java
- Future backend tasks

---

## Acceptance Criteria

- Java source generated from IR
- Valid Java class declaration
- Main method generated
- Deterministic output
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Statement generation
- Variable generation
- Spring Boot generation
- Java compilation
- Project generation
- File writing

---

## Branch

```
feature/task-032-java-class-generation
```

---

## Files to Create

```
app/backend/java/generator.py
tests/backend/test_java_generator.py
docs/architecture/backend.md
```

---

## Files to Modify

```
app/backend/__init__.py
```

(if required)

---

## AntiGravity Prompt

Implement TASK-032: IR → Java Class Generation.

Requirements:

- Do not create an implementation plan.
- Implement the complete feature directly.
- Create a Java backend generator that converts an IRProgram into a Java source string.
- Generate a deterministic Java class skeleton containing a public static void main(String[] args) method.
- Derive the Java class name from the IR program or module.
- Keep the implementation modular and independent of statement generation.
- Do not write files to disk.
- Produce backend diagnostics for invalid IR while failing gracefully.
- Add comprehensive unit tests covering empty programs, deterministic output, class generation, and main method generation.
- Update backend architecture documentation.

Before finishing:

- Run Ruff and fix all issues.
- Run Black and ensure formatting passes.
- Run MyPy and fix all typing issues.
- Run Pytest and ensure the full test suite passes.

Finally:

- Commit using a Conventional Commit message.
- Push the feature branch.
- Create a GitHub Pull Request.

Output only:

1. Branch name
2. Commit SHA
3. Pull Request URL