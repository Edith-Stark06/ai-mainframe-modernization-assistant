# TASK-025 — AST to IR Translation Foundation

## Objective

Implement the first AST-to-IR translation pass.

This task introduces the initial IR generation pipeline by translating the high-level program structure from the validated semantic model into the Intermediate Representation.

The goal is to establish the translation framework without yet handling executable statements.

---

## Background

The compiler currently provides:

- Lexer
- Parser
- AST
- Semantic Analysis
- Intermediate Representation (IR) Foundation

Task-025 begins constructing IR instances from the validated compiler front end.

---

## Scope

Translate structural elements only:

- Program
- Module
- Function
- Empty Basic Block

No executable COBOL statements are translated in this task.

---

## Functional Requirements

### 1. IRBuilder Implementation

Extend:

```
app/ir/builder.py
```

Implement:

```python
IRBuilder.build(...)
```

The builder should accept a validated `SemanticContext` and produce an `IRProgram`.

---

### 2. Translation

Generate:

```
SemanticContext
        │
        ▼
IRProgram
        │
        ▼
IRModule
        │
        ▼
IRFunction
        │
        ▼
IRBasicBlock(entry)
```

Each COBOL program should generate one module containing one function with an entry block.

---

### 3. Builder Separation

Keep translation logic inside dedicated helper methods such as:

- build_program()
- build_module()
- build_function()
- build_entry_block()

Avoid large monolithic methods.

---

### 4. Extensibility

Design the builder so future tasks can easily add:

- MOVE translation
- DISPLAY translation
- IF
- PERFORM
- GO TO
- CALL
- arithmetic statements

without redesign.

---

## Testing

Add tests covering:

- empty program translation
- single program
- module creation
- function creation
- entry basic block generation
- deterministic IR output

---

## Documentation

Update:

```
docs/architecture/intermediate-representation.md
```

Document:

- AST → IR translation
- builder responsibilities
- translation pipeline

---

## Acceptance Criteria

- IRBuilder produces valid IRProgram
- One module per COBOL program
- One function per module
- Entry basic block generated
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT translate:

- MOVE
- DISPLAY
- IF
- PERFORM
- GO TO
- CALL
- arithmetic statements
- optimization