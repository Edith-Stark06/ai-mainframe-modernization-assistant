# TASK-026 — IR Translation for MOVE Statements

## Objective

Extend the AST-to-IR translation pipeline to generate IR instructions for COBOL `MOVE` statements.

This task introduces the first executable IR instructions while preserving the separation between semantic analysis, IR generation, and future backend code generation.

---

## Background

The compiler currently supports:

- Lexer
- Parser
- AST
- Semantic Analysis
- IR Foundation
- Structural AST-to-IR Translation

Task-026 begins lowering executable COBOL statements into the Intermediate Representation.

---

## Scope

Translate supported `MOVE` statements into `IRMove` instructions and insert them into the appropriate entry basic block.

---

## Functional Requirements

### 1. Extend IRBuilder

Modify:

```
app/ir/builder.py
```

Implement translation of Procedure Division `MOVE` statements.

---

### 2. Statement Translation

For every valid COBOL `MOVE` statement:

```
MOVE source TO destination
```

Generate:

```
IRMove(
    source=<IR operand>,
    destination=<IR operand>,
)
```

Append the instruction to the current basic block.

---

### 3. Operand Translation

Introduce reusable helper methods for operand lowering.

Suggested methods:

- build_operand()
- build_variable_reference()
- build_literal()

Design these helpers so future translation of arithmetic expressions and CALL arguments can reuse them.

---

### 4. Semantic Integration

The builder should consume resolved symbols from the `SemanticContext` rather than reparsing identifiers.

No semantic validation should occur during IR generation.

---

### 5. Diagnostics

If an unsupported or incomplete MOVE statement is encountered, produce a structured IR translation diagnostic while continuing translation where possible.

---

## Testing

Add tests covering:

- MOVE variable → variable
- MOVE literal → variable
- Multiple MOVE statements
- Empty Procedure Division
- IR instruction ordering
- Deterministic IR generation

---

## Documentation

Update:

```
docs/architecture/intermediate-representation.md
```

Describe:

- MOVE lowering
- Operand translation
- IR instruction generation
- Relationship between semantic symbols and IR operands

---

## Acceptance Criteria

- Valid MOVE statements generate IRMove instructions
- Instructions appear in the correct basic block
- Translation consumes semantic information
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- DISPLAY
- ACCEPT
- Arithmetic translation
- IF
- PERFORM
- GO TO
- CALL
- Optimizations