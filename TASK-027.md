# TASK-027 — IR Translation for DISPLAY and ACCEPT Statements

## Objective

Extend the AST-to-IR translation pipeline to generate IR instructions for COBOL `DISPLAY` and `ACCEPT` statements.

This task expands the executable IR instruction set by introducing input/output operations while maintaining the separation between semantic analysis, IR generation, and backend code generation.

---

## Background

The compiler currently supports:

- Lexer
- Parser
- AST
- Semantic Analysis
- IR Foundation
- Structural AST-to-IR Translation
- MOVE Statement Translation

Task-027 adds translation for COBOL's primary console I/O statements.

---

## Scope

Translate supported:

- DISPLAY
- ACCEPT

statements into their corresponding IR instructions.

---

## Functional Requirements

### 1. Extend IR Instruction Hierarchy

Add instruction types:

```
IRDisplay
IRAccept
```

These should inherit from `IRInstruction`.

---

### 2. Extend IRBuilder

Modify:

```
app/ir/builder.py
```

Translate:

```
DISPLAY identifier
DISPLAY literal

ACCEPT identifier
```

into:

```
IRDisplay(...)
IRAccept(...)
```

Append generated instructions to the active basic block.

---

### 3. Operand Translation

Reuse the existing operand-building helpers introduced for MOVE.

Do not duplicate operand translation logic.

Supported operands:

- Variable references
- String literals
- Numeric literals

---

### 4. Semantic Integration

Use the validated `SemanticContext` for identifier resolution.

Do not perform semantic validation during IR generation.

---

### 5. Diagnostics

Emit structured IR translation diagnostics for:

- unsupported DISPLAY operands
- invalid ACCEPT targets
- unsupported statement variants

Continue translation after recoverable errors.

---

## Testing

Add tests covering:

- DISPLAY variable
- DISPLAY string literal
- DISPLAY numeric literal
- ACCEPT variable
- Multiple DISPLAY statements
- Mixed MOVE/DISPLAY/ACCEPT ordering
- Empty Procedure Division

---

## Documentation

Update:

```
docs/architecture/intermediate-representation.md
```

Document:

- DISPLAY lowering
- ACCEPT lowering
- IR I/O instruction model
- Operand reuse

---

## Acceptance Criteria

- DISPLAY generates IRDisplay
- ACCEPT generates IRAccept
- Instructions appear in order
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Arithmetic translation
- IF
- PERFORM
- GO TO
- CALL
- File I/O
- Optimizations