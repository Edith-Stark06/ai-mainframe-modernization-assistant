# TASK-030 — IR Translation for CALL Statements

## Objective

Extend the AST-to-IR translation pipeline to translate COBOL `CALL` statements into Intermediate Representation instructions.

This task completes the core executable IR by introducing inter-program invocation while maintaining a clean separation between semantic analysis, IR generation, and backend code generation.

---

## Background

The compiler currently supports:

- Lexer
- Parser
- AST
- Semantic Analysis
- IR Foundation
- Structural AST-to-IR Translation
- MOVE Translation
- DISPLAY Translation
- ACCEPT Translation
- Arithmetic Translation
- Control Flow Translation

Task-030 introduces external program invocation into the IR.

---

## Scope

Translate supported COBOL `CALL` statements into `IRCall` instructions.

Initially support:

- Literal program names
- Identifier program names (if represented by the AST)
- Positional USING arguments

Only the forms currently represented by the parser need to be translated.

---

## Functional Requirements

### 1. Extend IRBuilder

Modify:

```
app/ir/builder.py
```

Translate supported:

```
CALL "PROGRAM"
CALL "PROGRAM" USING A B C
CALL identifier
CALL identifier USING A B
```

into:

```
IRCall(
    target=...,
    arguments=[...]
)
```

Append generated instructions to the active basic block.

---

### 2. Operand Translation

Reuse the existing operand translation helpers.

Support:

- Variable references
- String literals
- Numeric literals

Do not duplicate translation logic.

---

### 3. Semantic Integration

Consume resolved symbols from the `SemanticContext`.

Do not perform semantic validation during IR generation.

---

### 4. Diagnostics

Produce structured IR translation diagnostics for:

- unsupported CALL forms
- missing targets
- unsupported USING clauses
- invalid operands

Continue translation where possible.

---

## Testing

Add tests covering:

- CALL literal
- CALL identifier
- CALL USING
- Multiple CALL statements
- Mixed executable statement ordering
- Deterministic IR generation

---

## Documentation

Update:

```
docs/architecture/intermediate-representation.md
```

Document:

- CALL lowering
- Argument translation
- External program invocation
- Relationship to future Java backend generation

---

## Acceptance Criteria

- CALL statements generate IRCall instructions
- USING arguments translated correctly
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Dynamic linking
- Java generation
- Optimization
- Call graph analysis